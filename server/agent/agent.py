"""The main agent loop.

Two entry points:
- CLI: `python -m server.agent.agent --task "..."` runs standalone.
- Library: `run_agent(message, emit)` is called from server/app/main.py with
  a callback that streams AgentEvents back to the WebSocket.

`emit` is a *sync* callback. When called from FastAPI, the app passes a
thread-safe shim that hands events to an asyncio.Queue on the main loop.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from typing import Any, Callable

# How long to wait after each action before taking the next screenshot,
# so the screen reflects what the action actually did. open_app fires
# off os.startfile which returns immediately while the app takes seconds
# to render; without this the model reasons over a stale frame and
# concludes "nothing happened, retry".
_POST_ACTION_DELAY: dict[str, float] = {
    "open_app":          4.0,
    "close_app":         0.7,
    "double_click":      1.5,   # often launches things
    "click":             0.5,
    "right_click":       0.4,
    "type":              0.2,
    "key":               0.2,
    "hotkey":            0.5,
    "scroll":            0.3,
    "set_volume":        0.4,
    "toggle_network":    2.0,
    "change_display_brightness": 0.3,
    "focus_window":      0.5,
    "minimize_all_windows": 0.4,
    "highlight_at":      0.0,   # purely visual, no settling needed
}

from shared.config import settings
from shared.protocol import (
    AgentEvent,
    SolutionRecord,
    SolutionStep,
    ToolCall,
    UserMessage,
)
from shared.security import cap_user_message, sanitize_for_prompt

EmitFn = Callable[[AgentEvent], None]


def _print_emit(event: AgentEvent) -> None:
    print(json.dumps({"kind": event.kind, "payload": event.payload}, default=str))


def _trim_old_screenshots(messages: list[dict], keep_last: int = 3) -> None:
    """Strip image_url parts from older user messages, keeping only the last N.

    The system + initial user message are always preserved as-is. Earlier
    user messages get their images replaced with a short placeholder so the
    context still has the action history but doesn't carry every screenshot.
    """
    # Find user messages that have an image attachment.
    image_indices: list[int] = []
    for i, m in enumerate(messages):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, list) and any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in content
        ):
            image_indices.append(i)
    if len(image_indices) <= keep_last:
        return
    # Replace all but the last `keep_last` image messages with text-only summaries.
    for idx in image_indices[:-keep_last]:
        parts = messages[idx].get("content", [])
        text_parts = [p for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        text = " ".join(p.get("text", "") for p in text_parts)[:500]
        messages[idx] = {"role": "user", "content": f"{text}\n[earlier screenshot omitted]"}


def run_agent(
    message: UserMessage,
    emit: EmitFn = _print_emit,
    *,
    mock_llm: bool = False,
    skip_db: bool = False,
    cancel_event: threading.Event | None = None,
    interrupt_event: threading.Event | None = None,
    keyboard_approved_event: threading.Event | None = None,
    mode: str = "control",
) -> SolutionRecord:
    """Run the loop to completion. Returns the SolutionRecord that was (or would be) saved."""
    from server.agent import computer
    from server.agent.llm import LLMClient, build_user_message
    from server.agent.tools import TOOL_SCHEMAS, dispatch, reset_session_limits

    # Defense: cap the user's prompt length BEFORE it touches anything
    # downstream, so a 200 KB document-paste can't smuggle a payload past
    # the rest of the pipeline.
    message = UserMessage(
        text=cap_user_message(message.text),
        attachments=message.attachments,
    )
    # Reset per-session limits (type-char cap, destructive-action cap).
    reset_session_limits()

    emit(AgentEvent(kind="status", payload={"msg": "Starting up"}))

    # 0. Preflight: executor connected. The LLM provider (OpenRouter) is
    # hit lazily on first chat call — no upfront probe.
    from server.app.bridge import bridge
    if not bridge.connected:
        msg = (
            "No Windows executor is connected. Run client/scripts/dev_all.ps1 "
            "on the Windows machine you want fixed; it will dial this backend "
            "and stay connected."
        )
        emit(AgentEvent(kind="error", payload={"msg": msg}))
        return SolutionRecord(problem_summary=message.text[:500], success=False)
    if not mock_llm and not (settings.llm_api_key.strip() or settings.openrouter_api_key.strip() or settings.gemini_api_key.strip()):
        msg = (
            "No API key is set (LLM_API_KEY, OPENROUTER_API_KEY, or GEMINI_API_KEY). "
            "Add one to your .env and restart the backend, or run with MOCK_LLM=1."
        )
        emit(AgentEvent(kind="error", payload={"msg": msg}))
        return SolutionRecord(problem_summary=message.text[:500], success=False)

    # 1. Hit the DB for a similar past solution.
    if not skip_db:
        try:
            from server.db.client import search_similar
            matches = search_similar(message.text, top_k=3)
            if matches and matches[0].score >= settings.similarity_threshold:
                emit(AgentEvent(
                    kind="status",
                    payload={"msg": "Found similar solution in DB", "score": matches[0].score},
                ))
                # CRITICAL: the DB row was written by a previous agent
                # run from a previous user. Treat it as fully untrusted —
                # strip injection markers and cap length before splicing
                # it back into the prompt.
                hint = sanitize_for_prompt(matches[0].record.problem_summary)
                if hint:
                    message = UserMessage(
                        text=f"{message.text}\n\n[hint from past run (untrusted): {hint}]",
                        attachments=message.attachments,
                    )
        except Exception as e:  # noqa: BLE001 — DB is best-effort
            emit(AgentEvent(kind="status", payload={"msg": f"DB lookup skipped: {e}"}))

    # 2. Initial screenshot + system + user.
    emit(AgentEvent(kind="status", payload={"msg": "Capturing your screen…"}))
    shot = computer.screenshot()
    emit(AgentEvent(kind="status", payload={"msg": "Thinking…"}))
    # `screen` is what the MODEL sees (post-resize). `display` is the actual
    # physical display. Click coords from the model are in screen-space and
    # must be scaled to display-space before dispatching to the executor.
    screen: tuple[int, int] = (int(shot.get("width", 1280)), int(shot.get("height", 720)))
    display: tuple[int, int] = (
        int(shot.get("display_width", screen[0])),
        int(shot.get("display_height", screen[1])),
    )

    def _scale_click(c: ToolCall) -> ToolCall:
        """Denormalize Qwen3-VL's [0, 1000] grounding output to display
        pixels. Clamp first so overshoots still land at the edge."""
        if c.name not in ("click", "double_click", "right_click", "highlight_at"):
            return c
        dw, dh = display
        sw, sh = screen
        try:
            raw_x = int(c.args.get("x", 0))
            raw_y = int(c.args.get("y", 0))
        except (TypeError, ValueError):
            print(
                f"[_scale_click] BAD args for {c.name}: args={c.args!r} "
                f"(image={sw}x{sh}, display={dw}x{dh})",
                flush=True,
            )
            return c
        cx = max(0, min(raw_x, 1000))
        cy = max(0, min(raw_y, 1000))
        x = int(cx / 1000 * dw)
        y = int(cy / 1000 * dh)
        # If the model emitted something WAY outside [0, 1000] it's
        # probably using image-pixel coords. Surface that interpretation
        # too so we can tell the cases apart from the log.
        if raw_x > 1100 or raw_y > 1100:
            as_pixel_x = max(0, min(raw_x, dw))
            as_pixel_y = max(0, min(raw_y, dh))
            print(
                f"[_scale_click] {c.name} raw=({raw_x},{raw_y}) "
                f"-> normalized=({x},{y})  pixel-fallback=({as_pixel_x},{as_pixel_y}) "
                f"| image={sw}x{sh} display={dw}x{dh} "
                f"** raw > 1100, model may be using IMAGE-PIXEL coords **",
                flush=True,
            )
        else:
            print(
                f"[_scale_click] {c.name} raw=({raw_x},{raw_y}) "
                f"-> ({x},{y}) | image={sw}x{sh} display={dw}x{dh}",
                flush=True,
            )
        new_args = dict(c.args)
        new_args["x"], new_args["y"] = x, y
        return ToolCall(name=c.name, args=new_args)
    llm = LLMClient(mock=mock_llm, mode=mode)
    # We REBUILD `messages` from scratch each turn (see top of the loop
    # below). Past tool results aren't accumulated, because feeding the
    # model "Tool X result: ok\nHere is the screen after the action"
    # turn after turn biases it to assume each action succeeded — it
    # then chains the next action on a wrong premise. Instead the
    # model gets: (1) system prompt, (2) the original user task, (3) a
    # plain-text list of what's been TRIED so far (no success verdict),
    # (4) the latest screenshot. It has to judge effects from the
    # current screen, not from a narrated history.
    action_log: list[str] = []
    latest_screen_b64: str = shot["image_b64"]
    # Guide-mode bookkeeping: track the most recent highlight target so
    # a follow-up `type(text=...)` can be re-rendered as a "Type: ..."
    # bubble at that exact spot. None in control mode (and at the start
    # of guide mode before any click has been emitted).
    last_guide_xy: tuple[int, int] | None = None
    messages: list[dict] = []  # rebuilt every iteration

    def _build_turn_messages() -> list[dict]:
        body = f"## User Instruction\n{message.text}\n\n"
        if action_log:
            body += "## Actions tried so far\n"
            body += "\n".join(f"{i+1}. {a}" for i, a in enumerate(action_log))
            body += (
                "\n(They may have worked, partially worked, or failed. "
                "Do NOT assume any of them succeeded — judge from the "
                "current screen below.)\n\n"
            )
        body += "## Current screen"
        return [
            {"role": "system", "content": llm.system_prompt},
            build_user_message(body, latest_screen_b64,
                               role_header=None, image_dims=screen),
        ]

    steps: list[SolutionStep] = []
    final_success = False
    final_summary = "Loop terminated without finish."

    # Tools that require explicit user permission in control mode.
    _MOUSE_KB_TOOLS = frozenset({
        "click", "double_click", "right_click", "scroll",
        "type", "key", "hotkey",
    })

    def _cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    def _interrupted() -> bool:
        return interrupt_event is not None and interrupt_event.is_set()

    def _keyboard_approved() -> bool:
        return keyboard_approved_event is None or keyboard_approved_event.is_set()

    def _wait_for_resume() -> bool:
        """Block until pause clears or cancel fires. Returns True if
        resumed (caller continues), False if cancelled (caller breaks)."""
        emit(AgentEvent(kind="status", payload={"msg": "paused"}))
        while _interrupted():
            if _cancelled():
                return False
            time.sleep(0.25)
        emit(AgentEvent(kind="status", payload={"msg": "resuming"}))
        return True

    for _ in range(settings.agent_max_steps):
        if _cancelled():
            emit(AgentEvent(kind="status", payload={"msg": "Stopped by user"}))
            emit(AgentEvent(kind="result", payload={"success": False, "summary": "Stopped by user."}))
            final_summary = "Stopped by user."
            break
        if _interrupted():
            # Paused before this turn started — just wait. On resume,
            # the next screenshot at the bottom of the previous iteration
            # is still fresh enough; we fall through to the LLM call.
            if not _wait_for_resume():
                continue   # loop top will hit _cancelled() and break

        # Rebuild the conversation from scratch this turn: system + a
        # single user message containing (task, action log, latest
        # screen). No accumulated tool-result narrative.
        messages = _build_turn_messages()

        # Stream the thought to the UI as it's generated.
        delta_started = {"v": False}
        def _on_delta(s: str) -> None:
            if not delta_started["v"]:
                delta_started["v"] = True
                emit(AgentEvent(kind="thought", payload={"text": "", "stream": True}))
            emit(AgentEvent(kind="thought_delta", payload={"text": s}))

        thought, calls = llm.chat(
            messages, TOOL_SCHEMAS, screen=screen, on_thought_delta=_on_delta,
            interrupt_event=interrupt_event,
        )
        # If pause fired mid-stream, the LLM call aborted with whatever
        # partial output we got. Drop the partial tool_call, wait for
        # resume, then take a fresh screenshot and loop back to think
        # again — the screen may have changed while paused.
        if _interrupted():
            if not _wait_for_resume():
                continue   # cancelled while paused → top of loop catches it
            try:
                fresh = computer.screenshot()
                if "width" in fresh and "height" in fresh:
                    screen = (int(fresh["width"]), int(fresh["height"]))
                if "display_width" in fresh and "display_height" in fresh:
                    display = (int(fresh["display_width"]), int(fresh["display_height"]))
                if fresh.get("image_b64"):
                    latest_screen_b64 = fresh["image_b64"]
            except Exception as e:  # noqa: BLE001
                emit(AgentEvent(kind="status",
                                payload={"msg": f"resume screenshot failed: {e}"}))
            continue
        # Only emit a non-streamed thought event when we *didn't* stream
        # (so it isn't duplicated when streaming already pushed deltas).
        if thought and not delta_started["v"]:
            emit(AgentEvent(kind="thought", payload={"text": thought}))

        if not calls:
            # Model produced text but no tool call. Don't bail — push back
            # and ask for a concrete action so multi-step tasks ("open
            # spotify and play X") keep going after intermediate wins.
            emit(AgentEvent(kind="status", payload={"msg":
                "Model didn't emit a tool call — asking for one."}))
            action_log.append(
                "(last turn: no tool call emitted — re-read the task, "
                "look at the current screen, and emit ONE concrete action)"
            )
            continue

        should_break_outer = False
        for call in calls:
            # Scale click-family coordinates from model-space to display-space.
            call = _scale_click(call)
            # Guide mode: swap clicks for a highlight; refuse anything that
            # would actually change the user's system (tools, hotkeys, type).
            if mode == "guide":
                click_kinds = ("click", "double_click", "right_click")
                allowed_meta = ("finish", "screenshot", "wait")
                if call.name in click_kinds:
                    label_map = {
                        "click": "click",
                        "double_click": "double-click",
                        "right_click": "right-click",
                    }
                    try:
                        x = int(call.args.get("x", 0))
                        y = int(call.args.get("y", 0))
                    except (TypeError, ValueError):
                        # Model emitted a list / bbox shape that the normalizer
                        # in llm.py didn't unpack. Skip this turn instead of
                        # crashing the whole run.
                        emit(AgentEvent(kind="status", payload={"msg":
                            f"skipped malformed {call.name}: args={call.args}"}))
                        action_log.append(
                            f"{call.name}({call.args!r}) -> REJECTED: "
                            f"x/y must be plain integers (not lists or bboxes)"
                        )
                        continue
                    # Remember the most recent guide click — if the model
                    # follows up with `type(text=...)` we'll anchor the
                    # text-hint bubble here.
                    last_guide_xy = (x, y)
                    call = ToolCall(
                        name="highlight_at",
                        args={"x": x, "y": y, "label": label_map[call.name], "seconds": 4.0},
                    )
                elif call.name == "type" and last_guide_xy is not None:
                    # The model wants the user to TYPE after the previous
                    # highlight. Re-render the spotlight at the same spot
                    # with a bubble showing the text — gives the user a
                    # visible prompt instead of forcing them to read the
                    # chat sidebar for the keystrokes.
                    text = str(call.args.get("text", "")).strip()
                    if text:
                        x, y = last_guide_xy
                        call = ToolCall(
                            name="highlight_at",
                            args={"x": x, "y": y, "label": "type",
                                  "seconds": 6.0, "type_hint": text},
                        )
                    else:
                        # Empty type — fall through to the standard rejection.
                        pass
                if call.name not in allowed_meta and call.name != "highlight_at" and call.name not in click_kinds:
                    # Forbidden action in guide mode (open_app, hotkey, type
                    # without a prior click, ...). Don't dispatch — that
                    # would do the task FOR the user. Tell the model what's
                    # allowed: clicks become highlights, and a `type` after
                    # a click renders a "Type: <text>" bubble at the spot.
                    emit(AgentEvent(kind="tool_call", payload=call.model_dump()))
                    steps.append(SolutionStep(action=call, note=thought or None))
                    rejection = {
                        "ok": False,
                        "error": (
                            f"Tool `{call.name}` is forbidden in guide mode. "
                            "Only click / double_click / right_click are "
                            "allowed (they become highlight overlays for the "
                            "user). To make the user type, first click(...) "
                            "the input field, then on the NEXT turn emit "
                            "type(text='...') — it will render a 'Type: ...' "
                            "bubble at the highlighted spot."
                        ),
                    }
                    emit(AgentEvent(kind="observation", payload=rejection))
                    fresh = computer.screenshot()
                    screen = (int(fresh.get("width", screen[0])),
                              int(fresh.get("height", screen[1])))
                    if "display_width" in fresh and "display_height" in fresh:
                        display = (int(fresh["display_width"]), int(fresh["display_height"]))
                    if fresh.get("image_b64"):
                        latest_screen_b64 = fresh["image_b64"]
                    action_log.append(
                        f"{call.name}({json.dumps(call.args)[:120]}) "
                        f"-> REJECTED in guide mode (only click/double_click/"
                        f"right_click allowed)"
                    )
                    continue
            # Permission gate: in control mode, keyboard/mouse tools require
            # explicit user approval before they run. Pause the agent and emit
            # a permission_request status so the UI can show a popup. Once the
            # user approves, keyboard_approved_event is set and interrupt is
            # cleared — we fall through and dispatch normally.
            if (
                mode == "control"
                and call.name in _MOUSE_KB_TOOLS
                and not _keyboard_approved()
            ):
                emit(AgentEvent(kind="status", payload={
                    "msg": f"Waiting for permission to use keyboard/mouse (tool: {call.name})",
                    "permission": "keyboard",
                    "tool": call.name,
                }))
                if interrupt_event is not None:
                    interrupt_event.set()
                if not _wait_for_resume():
                    break   # cancelled — loop top will break
                if _cancelled():
                    continue

            # Code-level guard: refuse two consecutive `wait`s. Prompt tells
            # the model the same thing, but defense-in-depth so a stubborn
            # model can't burn 10+ steps spinning on wait. Replaces the
            # second wait with a forced fresh screenshot + a strong push to
            # either act or call finish.
            if (
                call.name == "wait"
                and action_log
                and action_log[-1].startswith("wait(")
            ):
                try:
                    fresh = computer.screenshot()
                    if fresh.get("image_b64"):
                        latest_screen_b64 = fresh["image_b64"]
                        if "width" in fresh and "height" in fresh:
                            screen = (int(fresh["width"]), int(fresh["height"]))
                        if "display_width" in fresh and "display_height" in fresh:
                            display = (int(fresh["display_width"]),
                                       int(fresh["display_height"]))
                except Exception:  # noqa: BLE001
                    pass
                action_log.append(
                    "wait(...) -> SKIPPED: two waits in a row. The screen "
                    "above is current. Next turn MUST be either finish(...) "
                    "if the goal is visible, or a click/type/etc. to make "
                    "progress. Do NOT call wait again."
                )
                emit(AgentEvent(kind="status", payload={"msg":
                    "skipped a second consecutive wait — pick a different action"}))
                continue

            emit(AgentEvent(kind="tool_call", payload=call.model_dump()))
            result = dispatch(call, computer)
            # Graceful degradation: if we passed `type_hint` and the executor
            # is an older build that doesn't accept it, retry once WITHOUT
            # type_hint. The user gets the spotlight (no bubble) instead of
            # a hard failure that ends the run. Also stuff the hint into the
            # `label` so a slightly-newer mouse_guide.py can still render it.
            _err_str = (result.get("error") if isinstance(result, dict) else "") or ""
            if (
                "unexpected keyword argument 'type_hint'" in _err_str
                and call.name == "highlight_at"
                and "type_hint" in (call.args or {})
            ):
                fallback_args = {k: v for k, v in call.args.items() if k != "type_hint"}
                # Fold the hint into label so future mouse_guide.py builds
                # can still surface it even without the kwarg.
                fallback_args["label"] = f"Type: {call.args['type_hint']}"
                fallback_call = ToolCall(name="highlight_at", args=fallback_args)
                emit(AgentEvent(kind="status", payload={"msg":
                    "executor is older — retrying highlight without type_hint "
                    "(no bubble; restart executor to enable)"}))
                result = dispatch(fallback_call, computer)
                call = fallback_call
            steps.append(SolutionStep(action=call, note=thought or None))
            # Plain-text action-log entry for the next turn's user message.
            # We don't surface successful "ok"/"result" payloads — the model
            # is supposed to judge success from the next screenshot. But
            # we DO surface explicit dispatch errors, because for tools
            # like open_app the screen doesn't reflect the failure (app
            # didn't launch → desktop still visible → model can't tell)
            # and the model otherwise loops, re-emitting the same call.
            try:
                args_brief = json.dumps(call.args, default=str)[:120]
            except Exception:  # noqa: BLE001
                args_brief = str(call.args)[:120]
            _disp_err = (result.get("error") if isinstance(result, dict) else None)
            if _disp_err:
                action_log.append(
                    f"{call.name}({args_brief}) -> ERROR: {str(_disp_err)[:240]}"
                )
            else:
                action_log.append(f"{call.name}({args_brief})")

            # Generic anti-loop guard. If the model has called the same
            # tool 3 turns in a row, push back hard — the screen didn't
            # change enough to invalidate the prior attempt, so retrying
            # the same thing again is wasted budget. Forces a fresh
            # screenshot and a strong nudge to pivot.
            same_in_a_row = 0
            for entry in reversed(action_log):
                head = entry.split("(", 1)[0]
                if head == call.name:
                    same_in_a_row += 1
                else:
                    break
            if same_in_a_row >= 3:
                try:
                    fresh = computer.screenshot()
                    if fresh.get("image_b64"):
                        latest_screen_b64 = fresh["image_b64"]
                        if "width" in fresh and "height" in fresh:
                            screen = (int(fresh["width"]), int(fresh["height"]))
                        if "display_width" in fresh and "display_height" in fresh:
                            display = (int(fresh["display_width"]),
                                       int(fresh["display_height"]))
                except Exception:  # noqa: BLE001
                    pass
                action_log.append(
                    f"-> STOP REPEATING `{call.name}`. You have called it "
                    f"{same_in_a_row} times in a row with no progress. The "
                    f"screen above is fresh — pivot to a DIFFERENT action "
                    f"(different tool, or different args, or call finish "
                    f"if the goal isn't reachable). Do NOT emit `{call.name}` "
                    f"again on the next turn."
                )
                emit(AgentEvent(kind="status", payload={"msg":
                    f"breaking out of {call.name} loop (3 in a row) — pivoting"}))

            # HARD KILL: any rejection from the security layer in tools.py
            # ends the run. Covers shell/PowerShell injection, UNC paths,
            # unsafe URI schemes, the open_app blocklist, and per-session
            # caps. Without this the model just falls back to
            # suggest_solution() asking the user to do the dangerous thing
            # manually, or pivots to hotkey('win','r') + type to run the
            # rejected command via the Run dialog.
            #
            # dispatch() returns rejections as {"error": "..."} WITHOUT
            # setting "ok": False, so we trigger on the presence of an
            # "error" key whose value matches a known security phrase —
            # not on result.get("ok") which defaults True.
            err = result.get("error", "") if isinstance(result, dict) else ""
            err_lc = err.lower() if isinstance(err, str) else ""
            # Only ACTUALLY-dangerous rejections (injection / blocklist /
            # caps). Plain "app name not on allow-list" is recoverable —
            # the model should try a different name, not abort the run.
            SEC_PATTERNS = (
                "shell/powershell-like", "shell-like", "prompt-injection",
                "scripting host", "unc paths", "uri scheme",
                "permanent blocklist", "blocklist",
                "type() refused", "type() content rejected",
                "hotkey: ",  # length / shape rejections
                "session keystroke cap",
            )
            if err_lc and any(p in err_lc for p in SEC_PATTERNS):
                emit(AgentEvent(kind="observation", payload=result))
                refused = (
                    f"Refused: prompt-injection pattern blocked by security "
                    f"layer. The request asked the agent to call "
                    f"`{call.name}` with shell-like content ({err[:140]}). "
                    f"The run is ended; no fallback path (manual-type "
                    f"suggestion, open_app('cmd'), etc.) is permitted."
                )
                emit(AgentEvent(kind="error", payload={"msg": refused}))
                emit(AgentEvent(kind="result", payload={
                    "success": False, "summary": refused,
                }))
                final_success = False
                final_summary = refused
                break

            # Guide mode: the executor now BLOCKS during highlight_at until the
            # user clicks (or times out), so we fall through to the normal loop:
            # take a fresh screenshot, feed it back, model emits the next
            # highlight or calls finished() when the multi-step recipe is done.
            # We still surface dispatch failures explicitly so a missing proxy
            # doesn't look like silent success.
            if mode == "guide" and call.name == "highlight_at":
                ok = bool(result.get("ok")) if isinstance(result, dict) else False
                err = result.get("error") if isinstance(result, dict) else None
                if not ok and err:
                    emit(AgentEvent(kind="observation", payload=result))
                    emit(AgentEvent(kind="error", payload={"msg":
                        f"Couldn't highlight: {err}. "
                        "The executor on Windows didn't accept the highlight_at "
                        "call — make sure the latest executor is running."}))
                    emit(AgentEvent(kind="result",
                                    payload={"success": False,
                                             "summary": f"Highlight failed: {err}"}))
                    final_summary = f"Highlight failed: {err}"
                    break
                # Don't break — let the loop continue so the next highlight can
                # be shown after the user clicks. The model decides when to
                # call finished() based on the new screenshot.

            if call.name == "finish":
                # Two guard rails in control mode:
                #   * never accept ANY finish on turn 0 (no action yet);
                #   * never accept finish(success=False) until at least 3
                #     distinct attempted actions exist — failures are data,
                #     not a verdict, and the prompt promises to try ≥3
                #     different approaches before giving up.
                # EXCEPTION: a finish whose summary names a refused
                # injection pattern is a legitimate security refusal — let
                # it through immediately regardless of action count.
                attempted = [
                    s.action.name for s in steps
                    if s.action.name not in ("screenshot", "wait", "finish")
                ]
                attempted_actions = len(attempted)
                distinct_actions = len(set(attempted))
                finish_success = bool(call.args.get("success", False))
                finish_summary_lc = str(call.args.get("summary", "")).lower()
                is_security_refusal = (
                    not finish_success
                    and (
                        "prompt-injection" in finish_summary_lc
                        or "prompt injection" in finish_summary_lc
                        or "refused" in finish_summary_lc
                        or "attacker" in finish_summary_lc
                        or "evil-share" in finish_summary_lc
                        or "malicious" in finish_summary_lc
                        or "untrusted" in finish_summary_lc
                    )
                )
                if is_security_refusal:
                    final_success = False
                    final_summary = str(call.args.get("summary", ""))
                    emit(AgentEvent(kind="result", payload={
                        "success": False, "summary": final_summary,
                    }))
                    break

                if mode == "control" and attempted_actions == 0:
                    emit(AgentEvent(kind="status", payload={"msg":
                        "Model tried to finish without acting — pushing back."}))
                    action_log.append(
                        "finish() -> REJECTED (no action taken yet; emit a "
                        "concrete action like open_app/hotkey/click first)"
                    )
                    continue
                if mode == "control" and not finish_success and distinct_actions < 3:
                    tried = ", ".join(attempted) or "(none)"
                    emit(AgentEvent(kind="status", payload={"msg":
                        f"Model gave up after only {distinct_actions} different "
                        f"approach(es) — pushing back for more."}))
                    action_log.append(
                        f"finish(success=False) -> REJECTED — only "
                        f"{distinct_actions} distinct approach(es) tried "
                        f"({tried}). Need ≥3 genuinely different approaches "
                        f"before failure is acceptable. Pick a different tool."
                    )
                    continue
                final_success = bool(call.args.get("success", False))
                final_summary = str(call.args.get("summary", ""))
                emit(AgentEvent(
                    kind="result",
                    payload={"success": final_success, "summary": final_summary},
                ))
                break

            emit(AgentEvent(kind="observation", payload=result))

            # Always take a fresh screenshot after an action so the model sees
            # what actually happened, rather than reasoning over a stale frame.
            # Skip for `wait` which doesn't change the screen meaningfully.
        if should_break_outer:
            break

        if call.name not in ("screenshot", "wait"):
            # Settle: give the OS time to actually paint the action's result
            # before we grab a new frame. Per-action delays in _POST_ACTION_DELAY.
            delay = _POST_ACTION_DELAY.get(call.name, 0.4)
            if delay > 0:
                emit(AgentEvent(kind="status",
                                payload={"msg": f"waiting {delay:.1f}s for screen to settle…"}))
                time.sleep(delay)
            try:
                fresh = computer.screenshot()
                shot_result = {"ok": True, "result": fresh}
            except Exception as e:  # noqa: BLE001
                shot_result = {"ok": False, "error": str(e)}
                fresh = None
        elif call.name == "screenshot" and "result" in result:
            fresh = result["result"]
        else:
            fresh = None

        img_b64 = None
        if fresh:
            img_b64 = fresh.get("image_b64")
            if img_b64:
                latest_screen_b64 = img_b64
            if "width" in fresh and "height" in fresh:
                screen = (int(fresh["width"]), int(fresh["height"]))
            if "display_width" in fresh and "display_height" in fresh:
                display = (int(fresh["display_width"]), int(fresh["display_height"]))

        # NOTE: nothing is appended to `messages` here. The top of the
        # next loop iteration rebuilds messages from scratch via
        # _build_turn_messages() — system + (task + action_log +
        # latest_screen_b64). The model never sees a "Tool X result:
        # ok" narrative that would bias it to assume success.
    else:
        emit(AgentEvent(kind="error", payload={"msg": "max steps reached"}))

    record = SolutionRecord(
        problem_summary=message.text[:500],
        steps=steps,
        success=final_success,
        os="windows",
    )
    if final_success and not skip_db:
        try:
            from server.db.client import submit_pending_change
            # Sanitize anything we persist — `problem_summary` becomes a
            # future prompt hint for OTHER users, and `fix_description`
            # is rendered in the IT dashboard. Strip injection markers.
            safe_summary = sanitize_for_prompt(record.problem_summary, max_len=300)
            safe_fix = sanitize_for_prompt(final_summary, max_len=500)
            # Drop any steps the model produced that aren't on the
            # allow-list — defense against a poisoned mid-run state
            # writing forbidden tools back to disk. ALSO redact the
            # `text` field of every `type` step: whatever the agent
            # typed for THIS user (passwords, search queries, message
            # bodies, anything sensitive read off the screen) must
            # never leak into the shared DB for other users to
            # retrieve as a "hint". Same for `write_clipboard.text`.
            from server.agent.tools import _ALLOWED_TOOLS
            _SENSITIVE_ARG_TOOLS = {
                "type": "text",
                "write_clipboard": "text",
                "focus_window": "window_title",
                "search_files": "query",
            }
            safe_steps: list[dict[str, Any]] = []
            for s in record.steps:
                if s.action.name not in _ALLOWED_TOOLS:
                    continue
                action_dump = s.action.model_dump()
                redact_key = _SENSITIVE_ARG_TOOLS.get(s.action.name)
                if redact_key and isinstance(action_dump.get("args"), dict) \
                        and redact_key in action_dump["args"]:
                    action_dump["args"] = dict(action_dump["args"])
                    action_dump["args"][redact_key] = "<redacted>"
                safe_steps.append({
                    "action": action_dump,
                    "note": sanitize_for_prompt(s.note or "", 200),
                })
            steps_json = json.dumps(safe_steps)
            submit_pending_change(
                change_type="add",
                problem_summary=safe_summary,
                reason="Agent solved this automatically",
                submitted_by="agent",
                fix_description=safe_fix,
                steps_json=steps_json,
            )
            # Don't surface the DB write to the user-facing chat — the
            # "Solution submitted for Voodo approval" line was confusing
            # end users into thinking they had to wait. The IT/admin
            # dashboard remains the place to see pending submissions.
            print("[agent] solution submitted for Voodo approval (internal)", flush=True)
        except Exception as e:  # noqa: BLE001
            # Same: keep DB write failures out of the chat; just log.
            print(f"[agent] DB write skipped: {e}", flush=True)

    return record


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True, help="What the user wants fixed.")
    p.add_argument("--mock-llm", action="store_true", help="Use canned LLM responses.")
    p.add_argument("--skip-db", action="store_true", help="Don't talk to Postgres.")
    args = p.parse_args()
    run_agent(
        UserMessage(text=args.task),
        mock_llm=args.mock_llm,
        skip_db=args.skip_db,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
