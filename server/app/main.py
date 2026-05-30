"""FastAPI app: serves the chat UI and bridges the WebSocket to the agent.

The agent loop is fully synchronous (pyautogui, openai). We run it in a
worker thread and pipe its AgentEvents into an asyncio.Queue, then drain
the queue back to the WebSocket. This keeps the FastAPI event loop free.
"""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.app.bridge import bridge
from shared.config import settings
from shared.protocol import AgentEvent, UserMessage
from shared.security import cap_user_message

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="voodo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_DONE = object()  # sentinel pushed onto the queue when the agent run finishes

# Module-level subscriber set: every connected /ws receives agent events
# from every running session, not just the one it started. Lets the
# floating widget mirror what's happening regardless of whether the
# session was kicked off from the browser chat or the widget itself.
_subscribers: set[WebSocket] = set()
# Subset of _subscribers that identified themselves as the floating
# widget (via {"type":"hello","client":"widget"}). Used to:
#   • Skip the "open_assistant" call when a widget is already up.
#   • Auto-pause the in-flight run when the last widget WS drops.
_widget_subscribers: set[WebSocket] = set()
# A single in-flight session per backend instance. The events on this
# state (cancel / interrupt) are shared with the worker thread so any
# /ws subscriber can stop or pause the run.
_session: dict[str, threading.Event | None] = {"cancel": None, "interrupt": None, "keyboard_approved": None}


async def _broadcast(event: AgentEvent) -> None:
    """Fan an AgentEvent out to every connected /ws. Drops sockets that
    fail to receive (they'll get cleaned up on the next receive loop
    error anyway)."""
    if not _subscribers:
        return
    payload = event.model_dump()
    dead: list[WebSocket] = []
    for ws in _subscribers:
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001 — best-effort fan-out
            dead.append(ws)
    for ws in dead:
        _subscribers.discard(ws)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, bool | str]:
    return {"ok": True, "executor_connected": bridge.connected}


security = HTTPBasic()


def verify_it_password(credentials: HTTPBasicCredentials = Depends(security)):
    """Constant-time compare. FAIL CLOSED when IT_PASSWORD is unset —
    don't accept logins against an empty password."""
    import hmac

    if not settings.it_password:
        # Misconfig — deny everyone rather than silently accept "".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IT dashboard disabled (IT_PASSWORD not configured).",
        )
    user_ok = hmac.compare_digest(credentials.username, settings.it_username)
    pass_ok = hmac.compare_digest(credentials.password, settings.it_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": 'Basic realm="IT Dashboard"'},
        )
    return credentials.username


class _PendingChangeBody(BaseModel):
    type: str
    problem_summary: str
    reason: str
    fix_description: str | None = None
    solution_id: str | None = None


class _ReviewBody(BaseModel):
    note: str | None = None


@app.get("/it")
async def it_dashboard(username: str = Depends(verify_it_password)) -> FileResponse:
    return FileResponse(STATIC_DIR / "it.html")


@app.get("/api/solutions")
async def api_solutions(username: str = Depends(verify_it_password)):
    """Return every stored solution for the IT dashboard.

    Previously a single bad row (e.g. a stale tool name no longer in the
    `ToolName` Literal) crashed the whole endpoint with an opaque 500.
    Now the per-row decode is defensive (see `get_all_solutions`), and
    any remaining failure (DB unreachable, schema mismatch) returns a
    503 with the actual cause in the body so the dashboard can show
    something more useful than 'HTTP 500'."""
    import logging
    import traceback
    log = logging.getLogger("voodo.api")
    try:
        from server.db.client import get_all_solutions
        solutions = get_all_solutions(limit=100)
    except Exception as e:  # noqa: BLE001
        log.error("GET /api/solutions failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=503,
            detail=f"Solutions DB unavailable: {type(e).__name__}: {e}",
        )
    return [s.model_dump() for s in solutions]


@app.post("/api/pending-changes")
async def api_submit_pending_change(
    body: _PendingChangeBody,
    username: str = Depends(verify_it_password),
):
    from server.db.client import submit_pending_change
    return submit_pending_change(
        change_type=body.type,
        problem_summary=body.problem_summary,
        reason=body.reason,
        submitted_by=username,
        fix_description=body.fix_description,
        solution_id=body.solution_id,
    )


@app.get("/api/pending-changes")
async def api_get_pending_changes(_username: str = Depends(verify_it_password)):
    from server.db.client import get_pending_changes
    return get_pending_changes()


@app.get("/admin")
async def admin_dashboard(_username: str = Depends(verify_it_password)) -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/api/admin/pending-changes")
async def api_admin_get_pending_changes(_username: str = Depends(verify_it_password)):
    from server.db.client import get_pending_changes
    return get_pending_changes()


@app.delete("/api/pending-changes/{change_id}")
async def api_cancel_pending_change(
    change_id: str,
    _username: str = Depends(verify_it_password),
):
    from server.db.client import cancel_pending_change
    ok = cancel_pending_change(change_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Request not found or already reviewed")
    return {"ok": True}


@app.put("/api/admin/pending-changes/{change_id}/approve")
async def api_admin_approve(
    change_id: str,
    body: _ReviewBody,
    _username: str = Depends(verify_it_password),
):
    from server.db.client import approve_pending_change
    ok = approve_pending_change(change_id, reviewer_note=body.note)
    if not ok:
        raise HTTPException(status_code=404, detail="Change not found or already reviewed")
    return {"ok": True}


@app.put("/api/admin/pending-changes/{change_id}/reject")
async def api_admin_reject(
    change_id: str,
    body: _ReviewBody,
    _username: str = Depends(verify_it_password),
):
    from server.db.client import reject_pending_change
    ok = reject_pending_change(change_id, reviewer_note=body.note)
    if not ok:
        raise HTTPException(status_code=404, detail="Change not found or already reviewed")
    return {"ok": True}


@app.websocket("/executor")
async def ws_executor(ws: WebSocket) -> None:
    """Long-lived connection from the Windows executor.

    Auth (FAIL CLOSED): client sends `?token=<EXECUTOR_TOKEN>` as a
    query param. We REQUIRE EXECUTOR_TOKEN to be set on the server — if
    it isn't, every /executor connection is rejected. This stops the
    "empty .env" config from leaving the executor channel anonymous.
    """
    import hmac

    expected = settings.executor_token
    if not expected:
        # Server misconfig — refuse rather than accept anything.
        await ws.close(code=4500)
        return
    got = ws.query_params.get("token", "")
    # Constant-time compare to defeat timing oracles.
    if not hmac.compare_digest(got, expected):
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        await bridge.serve(ws, asyncio.get_running_loop())
    except WebSocketDisconnect:
        return


_current_task: asyncio.Task | None = None


@app.websocket("/ws")
async def ws_chat(ws: WebSocket) -> None:
    """Chat WebSocket. Accepts:
        {"type": "message", "text": "..."}  — start an agent run
        {"type": "stop"}                    — cancel the in-flight run
        {"type": "pause"}                   — interrupt-and-hold current run
        {"type": "resume"}                  — release a held run

    Stop and pause act on the SHARED `_session` events — any connected
    /ws can control the currently running session, and every connected
    /ws receives the event stream via _broadcast(). That way the
    floating widget mirrors browser-initiated runs (and vice versa).
    """
    global _current_task
    await ws.accept()
    _subscribers.add(ws)
    # Dev shortcuts (MOCK_AGENT / MOCK_LLM / SKIP_DB) are IGNORED in
    # VOODO_PROD=1 mode so a stray env var can't downgrade the deploy.
    if settings.prod_mode:
        use_mock_agent = False
        mock_llm = False
        skip_db = False
    else:
        use_mock_agent = os.getenv("MOCK_AGENT", "").lower() in ("1", "true", "yes")
        mock_llm = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")
        skip_db = os.getenv("SKIP_DB", "").lower() in ("1", "true", "yes")

    try:
        while True:
            data = await ws.receive_json()
            t = data.get("type")
            if t == "hello":
                # Client identification — currently the floating widget
                # uses this to register so we can auto-pause when it
                # closes. Browser clients don't send hello.
                if data.get("client") == "widget":
                    _widget_subscribers.add(ws)
                continue
            if t == "stop":
                ev = _session.get("cancel")
                if isinstance(ev, threading.Event):
                    ev.set()
                iev = _session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.clear()
                continue
            if t == "pause":
                iev = _session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.set()
                continue
            if t == "resume":
                iev = _session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.clear()
                continue
            if t == "set_mode":
                # Broadcast mode change to all connected clients
                await _broadcast(AgentEvent(kind="mode_change", payload={"mode": data.get("mode")}))
                continue
            if t == "approve_keyboard":
                # User granted keyboard/mouse access from the permission popup.
                # Mark approved and resume the paused agent in one step.
                kb_ev = _session.get("keyboard_approved")
                if isinstance(kb_ev, threading.Event):
                    kb_ev.set()
                iev = _session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.clear()
                continue
            if t == "feedback":
                # End-of-run 👍/👎 from the user. Persist to DB; no
                # round-trip status event back to the client (the UI
                # already shows the local "Thanks!" confirmation).
                rating = str(data.get("rating", "")).lower()
                if rating in ("like", "dislike"):
                    try:
                        from server.db.client import save_feedback
                        save_feedback(
                            rating=rating,
                            success=data.get("success"),
                            summary=data.get("summary"),
                            source=("widget" if ws in _widget_subscribers else "browser"),
                        )
                    except Exception as e:  # noqa: BLE001
                        print(f"[ws] feedback save failed: {e}", flush=True)
                continue
            if t != "message":
                continue
            text = data.get("text", "").strip()
            if not text:
                continue
            # Hard cap on user message length to neutralize huge-paste
            # injections at the front door (the agent caps again as
            # defense in depth).
            text = cap_user_message(text)
            # "guide" = show where to click only, don't act. "control" = act.
            mode = data.get("mode", "control")
            if mode not in ("control", "guide"):
                mode = "control"
            # A previous run is still alive. Two sub-cases:
            #   • Paused (interrupt_event set) — the user almost certainly
            #     abandoned the prior permission gate; treat the new
            #     message as an implicit stop+start.
            #   • Actively running — refuse with a visible error so the
            #     user knows to wait or hit Stop.
            if _current_task is not None and not _current_task.done():
                _iev = _session.get("interrupt")
                _paused = isinstance(_iev, threading.Event) and _iev.is_set()
                if _paused:
                    # Implicit cancel of the stuck-paused task.
                    _cev = _session.get("cancel")
                    if isinstance(_cev, threading.Event):
                        _cev.set()
                    if isinstance(_iev, threading.Event):
                        _iev.clear()  # let _wait_for_resume return
                    try:
                        await asyncio.wait_for(_current_task, timeout=2.0)
                    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                        pass
                    _current_task = None
                    # fall through to start the new run
                else:
                    await _broadcast(AgentEvent(kind="error", payload={
                        "msg": (
                            "A task is already running. Click the red Stop "
                            "button next to the input to cancel it, then "
                            "resend."
                        ),
                    }))
                    continue
            # Browser-initiated chat → minimize the voo.do tab and pop
            # the floating widget on the executor host. Fire-and-forget
            # so the chat itself isn't blocked if the executor is slow.
            # Skipped when the message came from the widget itself (it
            # already has focus) or when no executor is connected.
            if ws not in _widget_subscribers and bridge.connected:
                asyncio.create_task(_open_assistant_safe())
            cancel_event = threading.Event()
            interrupt_event = threading.Event()
            keyboard_approved_event = threading.Event()
            _session["cancel"] = cancel_event
            _session["interrupt"] = interrupt_event
            _session["keyboard_approved"] = keyboard_approved_event
            # Echo the user's prompt to every subscriber so widgets that
            # didn't originate the message still show "You: <prompt>".
            await _broadcast(AgentEvent(
                kind="status",
                payload={"msg": f"user: {text[:140]}", "user_prompt": text},
            ))
            _current_task = asyncio.create_task(_run_one_message(
                UserMessage(text=text),
                use_mock_agent=use_mock_agent,
                mock_llm=mock_llm,
                skip_db=skip_db,
                cancel_event=cancel_event,
                interrupt_event=interrupt_event,
                keyboard_approved_event=keyboard_approved_event,
                mode=mode,
            ))
    except WebSocketDisconnect:
        # This subscriber went away; don't cancel the session — other
        # subscribers may still be watching. Cancel only happens when
        # someone explicitly sends {"type":"stop"}.
        _on_subscriber_drop(ws)
        return
    except Exception:  # noqa: BLE001
        _on_subscriber_drop(ws)
        raise


def _on_subscriber_drop(ws: WebSocket) -> None:
    """Remove a /ws subscriber. If the dropped socket was the floating
    widget, auto-pause the in-flight run — closing the widget is the
    user's "wait, I want to think about this" signal."""
    _subscribers.discard(ws)
    was_widget = ws in _widget_subscribers
    _widget_subscribers.discard(ws)
    if was_widget and not _widget_subscribers:
        iev = _session.get("interrupt")
        if isinstance(iev, threading.Event):
            iev.set()


async def _open_assistant_safe() -> None:
    """Fire `open_assistant` on the executor side. Best-effort; swallows
    errors so a flaky executor never breaks the chat."""
    try:
        await bridge._call_async("open_assistant", {}, timeout=8.0)
    except Exception:  # noqa: BLE001
        pass


async def _run_one_message(
    message: UserMessage,
    *,
    use_mock_agent: bool,
    mock_llm: bool,
    skip_db: bool,
    cancel_event: threading.Event,
    interrupt_event: threading.Event | None = None,
    keyboard_approved_event: threading.Event | None = None,
    mode: str = "control",
) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event: AgentEvent) -> None:
        # Called from the worker thread — hop back to the FastAPI loop.
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def worker() -> None:
        try:
            if use_mock_agent:
                from server.app.mock_agent import run_mock_agent_sync
                run_mock_agent_sync(message, emit)
            else:
                from server.agent.agent import run_agent
                run_agent(
                    message, emit,
                    mock_llm=mock_llm, skip_db=skip_db,
                    cancel_event=cancel_event,
                    interrupt_event=interrupt_event,
                    keyboard_approved_event=keyboard_approved_event,
                    mode=mode,
                )
        except Exception as e:  # noqa: BLE001
            emit(AgentEvent(kind="error", payload={"msg": f"{type(e).__name__}: {e}"}))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    worker_task = asyncio.create_task(asyncio.to_thread(worker))
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            await _broadcast(item)
    finally:
        await worker_task
        # Release session state so the next prompt from any subscriber
        # can start a fresh run.
        _session["cancel"] = None
        _session["interrupt"] = None
        _session["keyboard_approved"] = None
