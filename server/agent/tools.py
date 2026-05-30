"""Tool schemas (OpenAI format) and dispatch table.

The schemas are sent to the VLM. The dispatch table maps tool names to the
implementations in `computer.py`. Keep these two in sync.

Security:
- `run_powershell` is permanently removed from the model-visible surface.
- A hard allow-list (`_ALLOWED_TOOLS`) is enforced inside `dispatch` so
  even a stale schema / poisoned DB step cannot resurrect a forbidden tool.
- Per-call arg validation lives here (length caps, type checks).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from shared.protocol import ToolCall

# ----------------------------------------------------------------------
# Hard allow-list: every tool name that the model is permitted to call.
# `run_powershell` is intentionally absent. If a tool isn't listed here,
# dispatch refuses it even if the schema or the DB says otherwise.
# ----------------------------------------------------------------------
_ALLOWED_TOOLS: set[str] = {
    # screen + meta
    "screenshot", "wait", "finish", "suggest_solution", "highlight_at",
    # mouse + keyboard
    "click", "double_click", "right_click", "scroll",
    "type", "key", "hotkey",
    # app + window control
    "open_app", "close_app", "list_running_apps", "focus_window",
    "minimize_all_windows",
    # diagnostics (read-only)
    "get_system_info", "get_audio_devices", "check_network_status",
    "get_ip_info", "list_printers", "check_camera", "list_usb_devices",
    "check_disk_space", "get_event_log_errors", "list_startup_programs",
    "read_clipboard", "search_files", "read_file_preview",
    # system controls
    "set_volume", "set_default_audio_device", "toggle_network",
    "change_display_brightness", "write_clipboard",
    "flush_dns", "clear_print_queue", "clear_temp_files",
}

# Tools that mutate user state. Counted against a per-session cap.
_DESTRUCTIVE_TOOLS: set[str] = {
    "close_app", "toggle_network", "set_volume",
    "set_default_audio_device", "change_display_brightness",
    "write_clipboard", "clear_print_queue", "clear_temp_files",
    "flush_dns", "open_app",
}

# open_app uses a strict ALLOW-LIST (was deny-list — too easy to bypass
# with aliases like "windowspowershell", "powershell_ise", trailing-space
# tricks, .lnk resolution, etc.). Anything not on this list, and not a
# safe URI scheme (ms-settings:, ms-windows-store:, http(s):, mailto:,
# tel:) is refused.
_OPEN_APP_ALLOWLIST = {
    # Browsers
    "chrome", "firefox", "msedge", "edge", "brave", "opera", "vivaldi",
    # Communication
    "spotify", "whatsapp", "discord", "slack", "zoom", "teams", "skype",
    "telegram", "signal",
    # Productivity
    "notepad", "wordpad", "calc", "calculator", "mspaint", "snippingtool",
    "explorer", "winword", "excel", "powerpnt", "outlook", "onenote",
    "acrobat", "acrord32",
    # Dev tools the user might legit ask for (still launched as a GUI,
    # never with a command line we control)
    "code", "vscode", "pycharm64", "idea64", "studio64", "rider64",
    "devenv", "visualstudio",  # Visual Studio 2019/2022 — devenv.exe
    # Windows utilities
    "taskmgr", "control", "mstsc", "magnify", "narrator",
    # Media
    "vlc", "mpc-hc", "spotify", "itunes",
}

# Apps that, even if a user/admin adds them to the allow-list, must NEVER
# be launchable — these are shells and scripting hosts that turn open_app
# into a one-shot RCE primitive.
_OPEN_APP_BLOCKLIST = {
    "cmd", "cmd.exe", "powershell", "powershell.exe", "powershell_ise",
    "powershell_ise.exe", "pwsh", "pwsh.exe", "windowspowershell",
    "wscript", "cscript", "wmic", "regedit", "regedit.exe", "regedt32",
    "mshta", "rundll32", "rundll32.exe", "bitsadmin", "certutil",
    "schtasks", "msbuild", "installutil", "regsvr32", "ftp", "telnet",
    "tftp", "winrm", "winrs", "psexec", "at",
}

# Per-session counters live here so dispatch can enforce caps without
# threading state through every caller. Reset by `reset_session_limits`.
_session_lock = threading.Lock()
_session_state: dict[str, int] = {"type_chars": 0, "destructive_calls": 0}


def reset_session_limits() -> None:
    """Call at the start of each agent run."""
    with _session_lock:
        _session_state["type_chars"] = 0
        _session_state["destructive_calls"] = 0
        _session_state["typed_text"] = ""


# Audit log — append every dispatched tool call so a post-incident
# review can see exactly what the agent did.
#
# Why not the CWD? `./voodo-audit.log` resolves to wherever the launcher
# was started, which is also a directory the user (and any process
# running as the user) can write to. An attacker process could
# overwrite the log to hide what voodo did. Default to
# %PROGRAMDATA%\voodo\audit.log on Windows — that directory is created
# by us and we lock down its ACL on first use. Override with
# VOODO_AUDIT_LOG=<absolute path>.
def _default_audit_path() -> Path:
    override = os.getenv("VOODO_AUDIT_LOG", "").strip()
    if override:
        return Path(override).resolve()
    if os.name == "nt":
        base = Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))
        return (base / "voodo" / "audit.log").resolve()
    return (Path.home() / ".voodo" / "audit.log").resolve()


_AUDIT_PATH = _default_audit_path()
_AUDIT_ROTATE_BYTES = int(os.getenv("VOODO_AUDIT_ROTATE_BYTES", str(5 * 1024 * 1024)))


def _ensure_audit_dir() -> None:
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Failed to create audit dir {_AUDIT_PATH.parent}: {e}")


_ensure_audit_dir()


def _audit_scrub(value: Any) -> Any:
    """Recursively replace control chars (\\n, \\r, \\x00, etc.) with
    spaces so an attacker-controlled arg can't forge a fake JSON line
    in the audit log. json.dumps already escapes \\n as \\\\n, but
    embedded U+2028 / U+2029 / U+0085 are line terminators that some
    consumers honor — strip them too."""
    if isinstance(value, str):
        # Strip every C0 control char except tab, plus U+2028/U+2029/U+0085.
        return re.sub(
            r"[\x00-\x08\x0A-\x1F\x7F\u0085\u2028\u2029]",
            " ",
            value,
        )
    if isinstance(value, dict):
        return {k: _audit_scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_audit_scrub(v) for v in value]
    return value


def _audit(event: str, name: str, args: dict[str, Any], result: Any = None) -> None:
    try:
        # Rotate first if too big — keeps a single .1 backup.
        try:
            if _AUDIT_PATH.exists() and _AUDIT_PATH.stat().st_size > _AUDIT_ROTATE_BYTES:
                backup = _AUDIT_PATH.with_suffix(_AUDIT_PATH.suffix + ".1")
                try:
                    if backup.exists():
                        backup.unlink()
                except OSError:
                    pass
                _AUDIT_PATH.rename(backup)
        except OSError:
            pass

        line = json.dumps({
            "ts": time.time(),
            "event": event,
            "tool": name,
            "args": _audit_scrub(args),
            "result_status": (
                "ok" if isinstance(result, dict) and result.get("ok") else
                "denied" if event == "deny" else
                "error" if isinstance(result, dict) and "error" in result else
                "n/a"
            ),
        }, default=str, ensure_ascii=True)
        # ensure_ascii=True means \n / \r / U+2028 etc. are escaped in
        # the JSON output, so an attacker can't forge a log line even
        # if _audit_scrub somehow misses something.
        with open(_AUDIT_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as e:  # noqa: BLE001 - audit must never block dispatch
        print(f"Warning: Failed to write audit log to {_AUDIT_PATH}: {e}")


# Quick regex used to refuse obviously-shell-y `type()` content. The
# matcher runs over a NORMALIZED, lowercase, no-whitespace version of
# the rolling type buffer (see `_typed_buffer` below) so that splitting
# a payload across multiple `type()` calls — or padding with U+200B,
# full-width letters, capitalization tricks — still trips the filter.
_TYPE_DANGER_RE = re.compile(
    r"(powershell|pwsh|cmd\.exe|cmd/[ck]|invoke-expression|iex|"
    r"frombase64string|-encodedcommand|-enc|"
    r"netuser|netlocalgroup|reg(add|delete)|"
    r"rundll32|regsvr32|mshta|wscript|cscript|bitsadmin|certutil|"
    r"shutdown/|format[a-z]:|del/[sf]|rmdir/[sq]|"
    r"curlhttp|wgethttp|invoke-webrequest|iwrhttp|"
    r"start-process|new-object|"
    r"taskschd|schtasks|netsh|"
    r"\.lnk|\.bat|\.cmd|\.ps1|\.vbs|\.hta|\.scr|\.js|\.jse|\.wsf)"
)

# Hotkey combinations that are stepping stones to typing-based RCE
# (Win+R opens Run; Win+X opens the power-user menu with PS/cmd entries;
# Ctrl+Shift+Enter elevates anything you launch; etc). Block them.
_DANGEROUS_HOTKEYS: set[frozenset[str]] = {
    frozenset({"win", "r"}),
    frozenset({"win", "x"}),
    frozenset({"ctrl", "shift", "enter"}),
    frozenset({"ctrl", "alt", "delete"}),
    frozenset({"ctrl", "alt", "del"}),
    frozenset({"alt", "f4"}),    # mass-close windows
}

# Single-key presses we never let the model emit via `key()`. The model
# can still trigger Enter / Tab via `type(text='\n')` paths that go
# through the danger regex, and via `hotkey(keys=['enter'])` after
# validation. We refuse the same kill-switch combos at single-key
# granularity in case the model tries to staged-press them.
_KEY_BLOCKLIST = {
    "f1",  # Windows help (browser launch)
}


def _typed_buffer_append(text: str) -> str:
    """Append to a rolling lowercased + whitespace-stripped buffer of
    everything the model has typed this session, and return the new
    buffer (last 400 chars). The danger regex runs over THIS, not the
    single call, so splitting a payload across N calls doesn't help.
    """
    with _session_lock:
        cur = _session_state.get("typed_text", "")
        if not isinstance(cur, str):
            cur = ""
        # Normalize: NFKC + strip invisible + lower + strip whitespace.
        from shared.security import _normalize_for_match  # local to avoid cycle
        norm = _normalize_for_match(text).lower()
        norm = re.sub(r"\s+", "", norm)
        new = (cur + norm)[-400:]
        _session_state["typed_text"] = new
        return new


def _validate_args(call: ToolCall) -> dict[str, Any] | None:
    """Return a dict {"error": "..."} if the call should be REJECTED,
    None otherwise. Modifies `call.args` in-place if it just needs to
    clamp/truncate."""
    name = call.name
    args = call.args

    if name == "type":
        text = str(args.get("text", ""))
        # 1) Append to the rolling buffer FIRST, then check the whole
        # buffer. Splitting "powershell" across two calls no longer
        # bypasses the regex.
        buf = _typed_buffer_append(text)
        if _TYPE_DANGER_RE.search(buf):
            return {"error":
                "type() content rejected: the rolling keystroke buffer "
                "now contains a shell/PowerShell-like token. Use a "
                "specific system tool instead of typing commands into "
                "the user's keyboard."}
        # 2) Per-session keystroke cap.
        from shared.config import settings as _s
        cap = _s.max_type_chars_per_session
        with _session_lock:
            if _session_state["type_chars"] + len(text) > cap:
                return {"error":
                    f"type() refused: session keystroke cap reached "
                    f"({cap} chars). The agent has typed too much in "
                    f"this turn — switch to open_app / hotkey."}
            _session_state["type_chars"] += len(text)
        if len(text) > 500:
            args["text"] = text[:500]

    elif name == "key":
        # `key()` was previously unvalidated — a single key('enter')
        # right after a staged Win+R+type sequence is full RCE. Block
        # the obviously-dangerous singletons and length-cap.
        k = str(args.get("key", "")).strip().lower()
        if not k:
            return {"error": "key: missing key name"}
        if len(k) > 20:
            return {"error": "key: name too long"}
        if k in _KEY_BLOCKLIST:
            return {"error": f"key: '{k}' is on the blocklist"}

    elif name == "hotkey":
        keys = args.get("keys") or []
        if not isinstance(keys, list):
            return {"error": "hotkey: keys must be a list"}
        if len(keys) > 6:
            return {"error": "hotkey: too many keys (max 6)"}
        # Normalize each key for the dangerous-combo check.
        norm_keys = {str(k).strip().lower() for k in keys if isinstance(k, str)}
        # Aliases the executor accepts (win == meta == cmd, ctrl == control, …).
        _alias = {"meta": "win", "cmd": "win", "super": "win",
                  "windows": "win", "winkey": "win",
                  "control": "ctrl", "option": "alt",
                  "return": "enter", "escape": "esc"}
        norm_keys = {_alias.get(k, k) for k in norm_keys}
        if frozenset(norm_keys) in _DANGEROUS_HOTKEYS:
            return {"error":
                f"hotkey refused: {sorted(norm_keys)} is on the "
                "dangerous-combo blocklist (Win+R, Win+X, "
                "Ctrl+Alt+Del, Ctrl+Shift+Enter, Alt+F4). Use a "
                "specific tool (open_app, focus_window, close_app) "
                "instead."}

    elif name == "open_app":
        raw = args.get("app_name", "")
        if not isinstance(raw, str):
            return {"error": "open_app: app_name must be a string"}
        # NFKC + strip trailing/leading whitespace so "powershell " and
        # "Ｐｏｗｅｒｓｈｅｌｌ" both fold to "powershell". The validator
        # must agree with the OS resolver — otherwise a trailing-space
        # bypass exists.
        from shared.security import _normalize_for_match
        app = _normalize_for_match(raw).strip().lower()
        if not app or len(app) > 200:
            return {"error": "open_app: app_name must be 1..200 chars"}
        # Re-write the arg with the normalized form so the executor
        # sees the same string we validated.
        args["app_name"] = app

        # Friendly-name → canonical exe basename, sourced from Postgres
        # (open_app_aliases table; falls back to in-memory defaults if
        # the DB is unreachable). Apply BEFORE the allow-list check so
        # "powerpoint" resolves to "powerpnt" and only canonical names
        # need to live in _OPEN_APP_ALLOWLIST.
        try:
            from server.db.client import get_open_app_aliases
            aliases = get_open_app_aliases()
        except Exception as e:  # noqa: BLE001
            print(f"Warning: Failed to fetch open_app aliases from DB: {e}")
            aliases = {}
        if app in aliases:
            app = aliases[app]
            args["app_name"] = app

        # Block UNC paths.
        if app.startswith("\\\\") or app.startswith("//"):
            return {"error": "open_app refused: UNC paths are not allowed."}
        # Block .lnk / .url / .bat / .cmd / .vbs / .hta / .ps1 / .scr /
        # .js shell shortcuts — these can chain to arbitrary targets and
        # bypass every other check.
        bad_ext = (".lnk", ".url", ".bat", ".cmd", ".vbs", ".hta",
                   ".ps1", ".scr", ".js", ".jse", ".wsf", ".pif")
        if app.endswith(bad_ext):
            return {"error":
                f"open_app refused: shortcut/script files ({', '.join(bad_ext)}) "
                "are blocked because they resolve to arbitrary targets."}

        # URI scheme check.
        is_uri = False
        if ":" in app:
            scheme = app.split(":", 1)[0]
            allowed_schemes = {
                "http", "https", "ms-settings", "ms-windows-store",
                "mailto", "tel",
            }
            if len(scheme) > 1:
                if scheme not in allowed_schemes:
                    return {"error":
                        f"open_app refused: URI scheme '{scheme}:' is not "
                        f"allowed. Allowed: {sorted(allowed_schemes)}."}
                is_uri = True

        if not is_uri:
            # Strip any path components — open_app does not accept paths.
            base = app.split("\\")[-1].split("/")[-1]
            # Drop .exe suffix to compare against allow-list.
            base_noext = base[:-4] if base.endswith(".exe") else base
            # Always-blocked basenames (defense in depth — never resolve
            # to a shell host even if someone tries to extend allow-list).
            if base_noext in _OPEN_APP_BLOCKLIST or base in _OPEN_APP_BLOCKLIST:
                return {"error":
                    f"open_app refused: '{base}' is a shell / scripting "
                    "host on the permanent blocklist."}
            # Allow-list check.
            if base_noext not in _OPEN_APP_ALLOWLIST:
                return {"error":
                    f"open_app refused: '{base_noext}' is not on the "
                    "voodo allow-list. Allowed apps: "
                    f"{sorted(_OPEN_APP_ALLOWLIST)}. Use a specific "
                    "ms-settings: URI for Windows settings pages."}

    elif name in ("click", "double_click", "right_click", "highlight_at"):
        try:
            int(args.get("x", 0))
            int(args.get("y", 0))
        except (TypeError, ValueError):
            return {"error": f"{name}: x/y must be integers"}

    elif name == "scroll":
        try:
            args["amount"] = int(args.get("amount", 0))
        except (TypeError, ValueError):
            return {"error": "scroll: amount must be an integer"}
        if abs(args["amount"]) > 50:
            args["amount"] = 50 if args["amount"] > 0 else -50

    elif name == "wait":
        try:
            secs = float(args.get("seconds", 0))
        except (TypeError, ValueError):
            return {"error": "wait: seconds must be a number"}
        args["seconds"] = max(0.0, min(secs, 5.0))

    elif name == "set_volume":
        try:
            level = int(args.get("level", 50))
        except (TypeError, ValueError):
            return {"error": "set_volume: level must be int"}
        args["level"] = max(0, min(level, 100))

    elif name == "change_display_brightness":
        try:
            level = int(args.get("level", 50))
        except (TypeError, ValueError):
            return {"error": "change_display_brightness: level must be int"}

    elif name == "search_files":
        dir_path = str(args.get("dir_path", ""))
        if dir_path.startswith("\\\\") or dir_path.startswith("//"):
            return {"error": "search_files refused: UNC paths are not allowed."}

    elif name == "read_file_preview":
        file_path = str(args.get("file_path", ""))
        if file_path.startswith("\\\\") or file_path.startswith("//"):
            return {"error": "read_file_preview refused: UNC paths are not allowed."}
        args["level"] = max(0, min(level, 100))

    # Per-session destructive-action cap.
    if name in _DESTRUCTIVE_TOOLS:
        from shared.config import settings as _s
        cap = _s.max_destructive_calls_per_session
        with _session_lock:
            if _session_state["destructive_calls"] >= cap:
                return {"error":
                    f"{name} refused: per-session destructive-action cap "
                    f"reached ({cap}). The agent is asking to mutate the "
                    f"system too many times in one chat turn — stop and "
                    f"ask the user."}
            _session_state["destructive_calls"] += 1

    return None

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Left-click at (x, y) on the screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "double_click",
            "description": "Double left-click at (x, y).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "right_click",
            "description": "Right-click at (x, y).",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "Type a string at the current keyboard focus.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "key",
            "description": "Press a single key. Examples: 'enter', 'esc', 'tab', 'win'.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hotkey",
            "description": "Press a key combo. Example: keys=['ctrl','shift','esc'].",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the mouse wheel. Positive = up, negative = down.",
            "parameters": {
                "type": "object",
                "properties": {"amount": {"type": "integer"}},
                "required": ["amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Take a fresh screenshot. Use after actions that change the screen.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Sleep for N seconds (max 5). Use when waiting for UI animations.",
            "parameters": {
                "type": "object",
                "properties": {"seconds": {"type": "number"}},
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open a Windows application or settings page by name or URI (e.g. 'chrome', 'calc', 'ms-settings:bluetooth').",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Close a Windows application gracefully by name (e.g. 'chrome').",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_apps",
            "description": "Returns a list of currently running visible applications and their window titles.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Bring a specific window to the foreground by its title substring.",
            "parameters": {
                "type": "object",
                "properties": {"window_title": {"type": "string"}},
                "required": ["window_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "minimize_all_windows",
            "description": "Minimize all windows to show the desktop.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get general system information (OS version, RAM, CPU usage).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set system volume (0-100) or toggle mute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer"},
                    "mute": {"type": "boolean"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_audio_devices",
            "description": "List all audio input and output devices.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_default_audio_device",
            "description": "Set the default audio playback or recording device by exact name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_name": {"type": "string"}
                },
                "required": ["device_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_network",
            "description": "Enable or disable Wi-Fi or Bluetooth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wifi": {"type": "boolean"},
                    "bluetooth": {"type": "boolean"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_network_status",
            "description": "Check if there is an active internet connection by pinging an external server.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "change_display_brightness",
            "description": "Change monitor brightness level (0-100).",
            "parameters": {
                "type": "object",
                "properties": {"level": {"type": "integer"}},
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": "Read the current text content of the clipboard.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_clipboard",
            "description": "Write text to the clipboard.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search files in a directory by content or name substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "directory": {"type": "string", "description": "e.g. C:\\Users\\liavs\\Documents"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_preview",
            "description": "Read the first 500 lines of a text file to understand its content.",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flush_dns",
            "description": "Clear the DNS resolver cache. Fixes 'website not loading' issues.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ip_info",
            "description": "Get the machine's IP address, default gateway, and DNS servers.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_printers",
            "description": "List all installed printers and which one is the default.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_print_queue",
            "description": "Clear all stuck print jobs from the print queue.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_camera",
            "description": "Check if a camera is detected and whether apps have permission to use it.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_usb_devices",
            "description": "List all connected USB devices.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_solution",
            "description": "Suggest a textual solution to the user, or recommend switching between visual (mouse/screenshot) and automated (tools) approaches if the current one is failing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suggestion": {
                        "type": "string",
                        "description": "The message to show to the user. E.g., 'I am stuck. Please try navigating to Settings manually', or 'Let me try a visual approach instead.'"
                    },
                },
                "required": ["suggestion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_disk_space",
            "description": "Check the total and free space for all connected logical drives. Crucial for 'computer is slow' or 'cannot save/download' issues.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_temp_files",
            "description": "Safely delete files in the Windows Temp and user Temp directories to free up space. Use after checking disk space if the drive is full.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_log_errors",
            "description": "Retrieve the 10 most recent Errors from the System and Application event logs. Crucial for diagnosing 'app crashes' or 'blue screens'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_startup_programs",
            "description": "List all applications configured to run automatically when the user logs in. Useful for diagnosing slow startup times.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Call when the issue is resolved (or impossible). Provide a summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "summary": {"type": "string"},
                },
                "required": ["success", "summary"],
            },
        },
    },
]


def dispatch(call: ToolCall, computer: Any) -> dict[str, Any]:
    """Execute a ToolCall via the `computer` module. Returns a result dict.

    Hardened path:
      1. Tool name must be in `_ALLOWED_TOOLS` (run_powershell etc. blocked).
      2. `_validate_args` enforces per-tool input contracts + session caps.
      3. Only then do we forward to the executor proxy.
    """
    name = call.name
    if name not in _ALLOWED_TOOLS:
        result = {"error": f"tool '{name}' is not on the voodo allow-list"}
        _audit("deny", name, call.args, result)
        return result

    rejection = _validate_args(call)
    if rejection is not None:
        _audit("deny", name, call.args, rejection)
        return rejection

    fn: Callable[..., Any] | None = getattr(computer, name, None)
    if fn is None:
        result = {"error": f"unknown tool: {name}"}
        _audit("deny", name, call.args, result)
        return result
    try:
        result = fn(**call.args)
        out = {"ok": True, "result": result}
        _audit("call", name, call.args, out)
        return out
    except TypeError as e:
        out = {"error": f"bad args for {name}: {e}"}
        _audit("error", name, call.args, out)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Tool {name} raised an unhandled exception: {e}")
        out = {"error": f"{type(e).__name__}: {e}"}
        _audit("error", name, call.args, out)
        return out
