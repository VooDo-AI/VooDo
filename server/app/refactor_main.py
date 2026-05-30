import re
import os

path = r"C:\Users\liavs\.gemini\antigravity-ide\brain\afac1d8a-c2c7-4b82-ba20-e17b9977b3ca\scratch\main.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Define ClientState and global _clients at the top
client_state_class = """
import uuid
import collections
class ClientState:
    def __init__(self):
        self.subscribers: set[WebSocket] = set()
        self.widget_subscribers: set[WebSocket] = set()
        self.session: dict[str, threading.Event | None] = {"cancel": None, "interrupt": None, "keyboard_approved": None}
        self.current_task: asyncio.Task | None = None
        self.queue = asyncio.Queue()

_clients: dict[str, ClientState] = collections.defaultdict(ClientState)

def _get_client_id(ws: WebSocket) -> str:
    # Use existing token/client_id query param or fallback to a default "default" for un-updated clients
    # In a real system, you'd reject clients without an ID or generate one and send it down.
    return ws.query_params.get("client_id", ws.query_params.get("token", "default"))
"""

# Find where to inject it. Let's put it after imports and _DONE.
content = content.replace(
    "_DONE = object()  # sentinel pushed onto the queue when the agent run finishes",
    "_DONE = object()  # sentinel pushed onto the queue when the agent run finishes" + "\n" + client_state_class
)

# Remove old globals
content = re.sub(r"_subscribers: set\[WebSocket\] = set\(\)\n", "", content)
content = re.sub(r"_widget_subscribers: set\[WebSocket\] = set\(\)\n", "", content)
content = re.sub(r'_session: dict\[str, threading\.Event \| None\] = \{"cancel": None, "interrupt": None, "keyboard_approved": None\}\n', "", content)
content = re.sub(r"_current_task: asyncio\.Task \| None = None\n", "", content)
content = re.sub(r"global _current_task\n", "", content)
# content = re.sub(r"queue = asyncio\.Queue\(\)\n", "", content) # queue might be local

# Now we need to replace all instances of:
# _subscribers -> state.subscribers
# _widget_subscribers -> state.widget_subscribers
# _session -> state.session
# _current_task -> state.current_task
# queue -> state.queue (wait, where is queue defined?)

# Wait, `queue` is defined locally in `ws_chat`? No, let's check how queue is used.
# If `queue` is defined locally in `ws_chat`, then we don't need it in ClientState.
# Let's save and we'll look at the file.

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
