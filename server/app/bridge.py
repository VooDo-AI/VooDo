"""ExecutorBridge — reverse-WS pipe between the agent loop and the
Windows executor.

The Windows side opens a persistent WebSocket to the backend's /executor
endpoint with a token. From then on, the agent loop calls
`bridge.call_sync(client_id, "click", {"x": 100, "y": 200})` and gets the result.

This removes the need for the backend-side .env to know any client IP.
The client tells us where it is by connecting to us.
"""
from __future__ import annotations

import asyncio
import itertools
from typing import Any

from fastapi import WebSocket


class ClientConnection:
    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop):
        self.ws = ws
        self.loop = loop
        self.pending: dict[int, asyncio.Future] = {}
        self.ids = itertools.count(1)
        self.lock = asyncio.Lock()


class ExecutorBridge:
    def __init__(self) -> None:
        # Maps client_id -> ClientConnection
        self._clients: dict[str, ClientConnection] = {}

    def is_connected(self, client_id: str) -> bool:
        return client_id in self._clients

    async def serve(self, ws: WebSocket, loop: asyncio.AbstractEventLoop, client_id: str) -> None:
        """Hold a single connection. If another arrives, the new one wins."""
        # Eject any prior connection cleanly.
        existing = self._clients.get(client_id)
        if existing is not None:
            try:
                await existing.ws.close(code=1000)
            except Exception:  # noqa: BLE001
                pass

        conn = ClientConnection(ws, loop)
        self._clients[client_id] = conn
        try:
            while True:
                msg = await ws.receive_json()
                req_id = msg.get("req_id")
                fut = conn.pending.pop(req_id, None) if req_id is not None else None
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        finally:
            # Drop the connection; fail any in-flight calls.
            if self._clients.get(client_id) is conn:
                del self._clients[client_id]
            for fut in conn.pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("executor disconnected"))
            conn.pending.clear()

    async def _call_async(
        self, client_id: str, name: str, args: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        conn = self._clients.get(client_id)
        if conn is None:
            raise RuntimeError(f"no executor connected for client_id {client_id}")
        req_id = next(conn.ids)
        fut = conn.loop.create_future()
        conn.pending[req_id] = fut
        async with conn.lock:
            await conn.ws.send_json({"req_id": req_id, "name": name, "args": args})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            conn.pending.pop(req_id, None)
            raise RuntimeError(f"executor call '{name}' timed out after {timeout}s") from None

    def call_sync(
        self,
        client_id: str,
        name: str,
        args: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Call from the agent worker thread. Blocks until the WS reply lands."""
        conn = self._clients.get(client_id)
        if conn is None:
            raise RuntimeError(
                f"No Windows executor is connected for {client_id}. Start the executor on "
                "your Windows machine (client/scripts/dev_all.ps1)."
            )
        fut = asyncio.run_coroutine_threadsafe(
            self._call_async(client_id, name, args or {}, timeout),
            conn.loop,
        )
        reply = fut.result(timeout=timeout + 5)
        if not reply.get("ok", False):
            raise RuntimeError(reply.get("error", "executor returned ok=false"))
        return reply.get("result", {})


# Singleton — imported by server/app/main.py (server side) and server/agent/computer.py (caller side).
bridge = ExecutorBridge()
