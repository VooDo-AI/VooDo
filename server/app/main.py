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

import collections

class ClientState:
    def __init__(self):
        self.subscribers: set[WebSocket] = set()
        self.widget_subscribers: set[WebSocket] = set()
        self.session: dict[str, threading.Event | None] = {"cancel": None, "interrupt": None, "keyboard_approved": None}
        self.current_task: asyncio.Task | None = None

_clients: dict[str, ClientState] = collections.defaultdict(ClientState)


async def _broadcast(client_id: str, event: AgentEvent) -> None:
    """Fan an AgentEvent out to every connected /ws for this client."""
    state = _clients[client_id]
    if not state.subscribers:
        return
    payload = event.model_dump()
    dead: list[WebSocket] = []
    for ws in state.subscribers:
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001 — best-effort fan-out
            dead.append(ws)
    for ws in dead:
        state.subscribers.discard(ws)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, bool | int]:
    return {"ok": True, "connected_clients": len(bridge._clients)}


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
    client_id = ws.query_params.get("client_id", "default")
    await ws.accept()
    try:
        await bridge.serve(ws, asyncio.get_running_loop(), client_id)
    except WebSocketDisconnect:
        return


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
    client_id = ws.query_params.get("client_id", "default")
    state = _clients[client_id]

    await ws.accept()
    state.subscribers.add(ws)
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
            msg_type = data.get("type")
            if msg_type == "hello" and data.get("client") == "widget":
                state.widget_subscribers.add(ws)
                continue
            if msg_type == "stop":
                ev = state.session.get("cancel")
                if isinstance(ev, threading.Event):
                    ev.set()
                iev = state.session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.clear()
                continue
            if msg_type == "pause":
                iev = state.session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.set()
                continue
            if msg_type == "resume":
                iev = state.session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.clear()
                continue
            if msg_type == "approve_keyboard":
                # User granted keyboard/mouse access from the permission popup.
                # Mark approved and resume the paused agent in one step.
                kb_ev = state.session.get("keyboard_approved")
                if isinstance(kb_ev, threading.Event):
                    kb_ev.set()
                iev = state.session.get("interrupt")
                if isinstance(iev, threading.Event):
                    iev.clear()
                continue
            if msg_type == "feedback":
                # End-of-run 👍/👎 from the user. Persist to DB; no
                # round-trip status event back to the client (the UI
                # already shows the local "Thanks!")
                rating = str(data.get("rating", "")).lower()
                if rating in ("like", "dislike"):
                    try:
                        from server.db.client import save_feedback
                        save_feedback(
                            rating=rating,
                            success=data.get("success"),
                            summary=data.get("summary"),
                            source=("widget" if ws in state.widget_subscribers else "browser"),
                        )
                    except Exception as e:  # noqa: BLE001
                        print(f"[ws] feedback save failed: {e}", flush=True)
                continue
            if msg_type != "message":
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
            # 2) Guard concurrent runs.
            #     Not running - start a new task.
            #     Done        - garbage collect the old task, start a new one.
            #                 (No await needed; we just let asyncio clean it up)
            #     Paused      - resume the paused task, DO NOT start a new one, treat the
            #     message as an implicit stop+start.
            #     Actively running - refuse with a visible error so the
            #     user knows to wait or hit Stop.
            if state.current_task is not None and not state.current_task.done():
                _iev = state.session.get("interrupt")
                _paused = isinstance(_iev, threading.Event) and _iev.is_set()
                if _paused:
                    # Cancel the paused task implicitly.
                    _cev = state.session.get("cancel")
                    if isinstance(_cev, threading.Event):
                        _cev.set()
                    if isinstance(_iev, threading.Event):
                        _iev.clear()  # let _wait_for_resume return
                    try:
                        await asyncio.wait_for(state.current_task, timeout=2.0)
                    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                        pass
                    state.current_task = None
                    # fall through to start the new run
                else:
                    await _broadcast(client_id, AgentEvent(kind="error", payload={
                        "msg": (
                            "A task is already running. Click the red Stop "
                            "button next to the input to cancel it, then "
                            "try again."
                        )
                    }))
                    continue

            # Browser-initiated chat -> minimize the voo.do tab and pop
            # the floating widget on the executor host.
            if ws not in state.widget_subscribers and bridge.is_connected(client_id):
                asyncio.create_task(_open_assistant_safe(client_id))

            # 3) Setup a fresh session.
            cancel_event = threading.Event()
            interrupt_event = threading.Event()
            keyboard_approved_event = threading.Event()
            state.session["cancel"] = cancel_event
            state.session["interrupt"] = interrupt_event
            state.session["keyboard_approved"] = keyboard_approved_event

            # Echo the user's prompt to every subscriber so widgets that
            # didn't originate the message still show "You: <prompt>".
            await _broadcast(client_id, AgentEvent(
                kind="status",
                payload={"msg": f"user: {text[:140]}", "user_prompt": text},
            ))
            state.current_task = asyncio.create_task(_run_one_message(
                UserMessage(text=text),
                use_mock_agent=use_mock_agent,
                mock_llm=mock_llm,
                skip_db=skip_db,
                cancel_event=cancel_event,
                interrupt_event=interrupt_event,
                keyboard_approved_event=keyboard_approved_event,
                mode=mode,
                ws=ws,
                client_id=client_id,
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
        widget, auto-pause the in-flight run - closing the widget is the
        user's "wait, I want to think about this" signal."""
        state.subscribers.discard(ws)
        was_widget = ws in state.widget_subscribers
        state.widget_subscribers.discard(ws)
        if was_widget and not state.widget_subscribers:
            iev = state.session.get("interrupt")
            if isinstance(iev, threading.Event):
                iev.set()


async def _open_assistant_safe(client_id: str) -> None:
    """Fire `open_assistant` on the executor side. Best-effort; swallows
    errors so a flaky executor never breaks the chat."""
    try:
        await bridge._call_async(client_id, "open_assistant", {}, timeout=8.0)
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
    ws: WebSocket,
    client_id: str = "default",
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
                    client_id=client_id,
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
            await _broadcast(client_id, item)
    finally:
        await worker_task
        # Release session state so the next prompt from any subscriber
        # can start a fresh run.
        # Note: _run_one_message is top-level, so we must access state via _clients[client_id]
        state = _clients[client_id]
        state.session["cancel"] = None
        state.session["interrupt"] = None
        state.session["keyboard_approved"] = None
