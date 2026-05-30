"""Windows side-effects: screenshot, mouse, keyboard, shell.

These functions actually touch the local OS. They run on the user's Windows
box inside the executor service; the agent (which may be on a different
host) drives them over the WebSocket opened by main.py.

Security model
--------------
* `run_powershell` is NOT a public tool. Every internal call to PS uses
  `_run_ps_internal` with a fixed script body + env-passed user args.
* String args that ultimately become process arguments (taskkill /IM,
  pyautogui.typewrite, ...) are validated against
  `shared.security.validate_ps_arg`.
* File paths for `read_file_preview` / `search_files` must resolve under
  the allow-list in `shared.security.validate_file_path`.
"""
from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import sys
import time
from typing import Any

from shared.security import validate_file_path, validate_ps_arg


# Windows + high-DPI displays: by default Python is NOT DPI-aware, so mss
# captures at physical pixels (e.g. 3072x1920) but pyautogui clicks at
# logical pixels (e.g. 1920x1200 if scaling=160%). The two coord systems
# disagree, clicks land in the wrong place. Telling Windows we ARE
# DPI-aware makes both libraries operate on physical pixels — single
# coordinate system, screenshots and clicks line up.
def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # PROCESS_PER_MONITOR_DPI_AWARE = 2.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        # Older Windows: fall back to user32 SetProcessDPIAware.
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_enable_dpi_awareness()


def _pyautogui():
    import pyautogui
    # FAILSAFE ON — moving the mouse to a screen corner raises and aborts
    # whatever the agent is doing. This is the user's panic button.
    pyautogui.FAILSAFE = True
    return pyautogui


# --- Internal-only PowerShell runner ---------------------------------
# `run_powershell` is no longer exposed to the model. This helper is
# called ONLY by the trusted diagnostic functions below (flush_dns,
# list_printers, check_disk_space, etc.) and never sees model output.
# All user/model-controlled string args MUST be passed via the `env`
# dict — never f-string-interpolated into the script body.

def _run_ps_internal(
    script: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> "subprocess.CompletedProcess[str]":
    """Run a FIXED PowerShell script with extra env vars exposed to it.

    Inside `script`, reference user-controlled values as `$env:VOODO_X`
    — never substitute them with an f-string. This eliminates the
    single-quote escape attack class.
    """
    full_env = dict(os.environ)
    if env:
        for k, v in env.items():
            if not k.startswith("VOODO_"):
                raise ValueError(f"untrusted env var must start with VOODO_: {k}")
            full_env[k] = str(v)
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=full_env,
    )


# Window-title substrings that mean "this is the voodo chat UI" and should
# be hidden from screenshots so the model doesn't try to click its own logs.
_VOODO_TITLE_MARKERS = ("voo.do", "voodo")


def _hide_voodo_windows() -> int:
    """Minimize every visible top-level window whose title looks like the
    voodo chat. Best-effort: any failure is swallowed so a screenshot still
    happens. Returns the count of windows minimized.
    """
    try:
        import pygetwindow as gw
    except ImportError:
        return 0
    n = 0
    try:
        wins = gw.getAllWindows()
    except Exception:  # noqa: BLE001
        return 0
    for w in wins:
        title = (getattr(w, "title", "") or "").lower()
        if not any(m in title for m in _VOODO_TITLE_MARKERS):
            continue
        try:
            if not w.isMinimized:
                w.minimize()
                n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def screenshot() -> dict[str, Any]:
    """Capture the primary screen at native resolution.

    No resizing, no coord translation — the image goes to the model
    exactly as captured, the model emits coords in that same space,
    and the agent dispatches them straight to pyautogui.

    DPI awareness (SetProcessDpiAwareness(2) at module load) keeps the
    capture and the click in the same coordinate system on high-DPI
    monitors.

    Set VOODO_HIDE_OWN_WINDOWS=1 to minimize voodo windows before
    grabbing (off by default — keeping the chat visible is usually
    more useful for debugging).
    """
    from mss import mss
    from PIL import Image

    hide = os.getenv("VOODO_HIDE_OWN_WINDOWS", "").lower() in ("1", "true", "yes")
    hidden = _hide_voodo_windows() if hide else 0
    if hidden:
        time.sleep(0.25)

    with mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.rgb)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "image_b64": base64.b64encode(buf.getvalue()).decode(),
        "width": img.width,
        "height": img.height,
        # display_* kept for backward compat with agent code that
        # still reads them; values are identical to width/height now
        # since no resize happens.
        "display_width": img.width,
        "display_height": img.height,
        "hidden_voodo_windows": hidden,
    }


def click(x: int, y: int) -> dict[str, Any]:
    _pyautogui().click(x=x, y=y)
    return {"x": x, "y": y}


def double_click(x: int, y: int) -> dict[str, Any]:
    _pyautogui().doubleClick(x=x, y=y)
    return {"x": x, "y": y}


def right_click(x: int, y: int) -> dict[str, Any]:
    _pyautogui().rightClick(x=x, y=y)
    return {"x": x, "y": y}


def type(text: str) -> dict[str, Any]:  # noqa: A001 — matches tool name
    if not isinstance(text, str):
        return {"error": "type: text must be a string"}
    if "\x00" in text:
        return {"error": "type: null bytes not allowed"}
    text = text[:500]
    _pyautogui().typewrite(text, interval=0.02)
    return {"typed_len": len(text)}


def key(key: str) -> dict[str, Any]:  # noqa: A002
    _pyautogui().press(key)
    return {"key": key}


def hotkey(keys: list[str]) -> dict[str, Any]:
    _pyautogui().hotkey(*keys)
    return {"keys": keys}


def scroll(amount: int) -> dict[str, Any]:
    _pyautogui().scroll(amount)
    return {"amount": amount}


# NOTE: `run_powershell` is intentionally absent. PowerShell is no longer
# a model-callable tool. Each previously PowerShell-based fix is now
# served by a specific function with a FIXED script body.


def wait(seconds: float) -> dict[str, Any]:
    seconds = min(max(float(seconds), 0), 5.0)
    time.sleep(seconds)
    return {"slept": seconds}


# Allow-list (kept in sync with server/agent/tools.py::_OPEN_APP_ALLOWLIST).
# Defense in depth: the agent-side `dispatch` already filters before
# the call gets here, but we re-validate so a misconfigured / older
# agent can't push a forbidden name through.
_OPEN_APP_ALLOWLIST = {
    "chrome", "firefox", "msedge", "edge", "brave", "opera", "vivaldi",
    "spotify", "whatsapp", "discord", "slack", "zoom", "teams", "skype",
    "telegram", "signal",
    "notepad", "wordpad", "calc", "calculator", "mspaint", "snippingtool",
    "explorer", "winword", "excel", "powerpnt", "outlook", "onenote",
    "acrobat", "acrord32",
    "code", "vscode", "pycharm64", "idea64", "studio64", "rider64",
    "devenv", "visualstudio",  # Visual Studio 2019/2022 — devenv.exe
    "taskmgr", "control", "mstsc", "magnify", "narrator",
    "vlc", "mpc-hc", "itunes",
}
_OPEN_APP_BLOCKLIST = {
    "cmd", "cmd.exe", "powershell", "powershell.exe", "powershell_ise",
    "powershell_ise.exe", "pwsh", "pwsh.exe", "windowspowershell",
    "wscript", "cscript", "wmic", "regedit", "regedit.exe", "regedt32",
    "mshta", "rundll32", "rundll32.exe", "bitsadmin", "certutil",
    "schtasks", "msbuild", "installutil", "regsvr32", "ftp", "telnet",
    "tftp", "winrm", "winrs", "psexec", "at",
}
_OPEN_APP_ALLOWED_SCHEMES = {
    "http", "https", "ms-settings", "ms-windows-store",
    "mailto", "tel",
}
_OPEN_APP_BAD_EXTS = (
    ".lnk", ".url", ".bat", ".cmd", ".vbs", ".hta", ".ps1",
    ".scr", ".js", ".jse", ".wsf", ".pif",
)


def open_app(app_name: str) -> dict[str, Any]:
    r"""Launch an application, file, or system URI — with input validation.

    Rejects:
      * non-strings, empty, >200 chars
      * shell hosts (cmd/powershell/wscript/regedit/mshta/...)
      * UNC paths (\\server\share\thing.exe)
      * URI schemes outside the allow-list
      * arguments (we never pass a command-line — `os.startfile` doesn't
        take args, and we don't add any)

    Tries `os.startfile` first; falls back to a Win+R typed launch ONLY
    if startfile failed AND the name has no path-like or URI-like
    characters (so we don't end up typing arbitrary commands into the
    Run dialog).
    """
    import os as _os
    import unicodedata

    if not isinstance(app_name, str):
        return {"error": "open_app: app_name must be a string"}
    # NFKC + strip to defeat full-width / trailing-space tricks. The
    # validator and ShellExecute must agree on the string.
    name = unicodedata.normalize("NFKC", app_name).strip()
    if not name or len(name) > 200:
        return {"error": "open_app: app_name must be 1..200 chars"}
    # Block control chars / null / newline / shell metachars / quotes /
    # spaces (no app should need them — paths are not allowed here).
    for ch in "\x00\n\r\t`;&|<>\"' ":
        if ch in name:
            return {"error": f"open_app: forbidden char {ch!r} in app_name"}

    low = name.lower()

    # UNC paths — never.
    if low.startswith("\\\\") or low.startswith("//"):
        return {"error": "open_app: UNC paths are not allowed"}

    # Block shortcut / script extensions — they chain to arbitrary targets.
    if low.endswith(_OPEN_APP_BAD_EXTS):
        return {"error":
            f"open_app: shortcut/script file extensions are blocked"}

    # URI scheme path: validate, then dispatch via os.startfile and return.
    if ":" in low:
        scheme = low.split(":", 1)[0]
        if len(scheme) > 1:
            if scheme not in _OPEN_APP_ALLOWED_SCHEMES:
                return {"error":
                    f"open_app: URI scheme '{scheme}:' is not allowed. "
                    f"Allowed: {sorted(_OPEN_APP_ALLOWED_SCHEMES)}"}
            try:
                _os.startfile(name)
                return {"status": "opened", "method": "uri", "app_name": name}
            except OSError as e:
                return {"error": f"open_app uri failed: {e}"}

    # Plain-name path: strip path components, drop .exe, allow-list check.
    # Friendly-name → canonical mapping (powerpoint→powerpnt etc.) is
    # done on the agent side from the Postgres open_app_aliases table
    # BEFORE the call reaches us, so we only deal with canonical names.
    base = low.split("\\")[-1].split("/")[-1]
    base_noext = base[:-4] if base.endswith(".exe") else base
    if base_noext in _OPEN_APP_BLOCKLIST or base in _OPEN_APP_BLOCKLIST:
        return {"error":
            f"open_app: '{base}' is on the permanent blocklist"}
    if base_noext not in _OPEN_APP_ALLOWLIST:
        return {"error":
            f"open_app: '{base_noext}' is not on the allow-list "
            f"({len(_OPEN_APP_ALLOWLIST)} apps). Use an ms-settings: URI "
            f"for Windows settings pages."}

    errs: list[str] = []

    # 1. os.startfile by allow-listed basename — resolves via PATH /
    # App Paths registry. Refuse anything that resolves to a .lnk-style
    # target (we can't introspect the resolution, so we rely on the
    # allow-list to ensure the name itself is a real executable name).
    try:
        _os.startfile(base_noext)
        return {"status": "opened", "method": "startfile", "app_name": base_noext}
    except OSError as e:
        errs.append(f"startfile: {e}")
    except Exception as e:  # noqa: BLE001
        errs.append(f"startfile: {type(e).__name__}: {e}")

    # 2. Win+R typed launch — only if name is a plain identifier AND on
    # the allow-list. We refuse to type anything we didn't sanitize.
    if re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", base_noext):
        try:
            pg = _pyautogui()
            pg.hotkey("win", "r")
            time.sleep(0.4)
            pg.typewrite(base_noext, interval=0.02)
            time.sleep(0.15)
            pg.press("enter")
            return {"status": "opened", "method": "win_r_typed",
                    "app_name": base_noext}
        except Exception as e:  # noqa: BLE001
            errs.append(f"win_r_typed: {type(e).__name__}: {e}")

    return {"error": f"Failed to open '{base_noext}'. Tried: " + " | ".join(errs)}


def close_app(app_name: str) -> dict[str, Any]:
    """Close an application gracefully.

    `app_name` is validated as a plain image-name string (alnum + dot +
    dash + underscore, max 64 chars). taskkill is invoked with a list-arg
    `subprocess.run` (no shell), so the only injection surface is the
    image-name itself — we lock that down with a regex.
    """
    if not isinstance(app_name, str) or not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", app_name):
        return {"error": "close_app: app_name must match [A-Za-z0-9_.-], max 64 chars"}
    target = app_name if app_name.lower().endswith(".exe") else f"{app_name}.exe"

    proc = subprocess.run(
        ["taskkill", "/IM", target, "/T", "/F"],
        capture_output=True,
        text=True,
    )
    return {
        "status": "close command sent",
        "app_name": app_name,
        "exit_code": proc.returncode,
    }


def list_running_apps() -> dict[str, Any]:
    script = r"Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object Name, MainWindowTitle | ConvertTo-Json"
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    import json
    try:
        data = json.loads(proc.stdout)
        return {"apps": data}
    except Exception:
        return {"apps": [], "raw": proc.stdout}


def focus_window(window_title: str) -> dict[str, Any]:
    """Bring a window to the foreground by title substring.

    Specificity rule: when multiple windows contain the needle, the
    LONGEST title wins. This prevents focus_window('Zoom') from
    landing on the plain "Zoom" workspace when "Zoom Meeting" also
    exists — the model gets the most-specific candidate by default,
    matching what users almost always mean.

    Returns the actually-focused title plus all candidate matches so
    the agent can verify (and the action_log shows what happened).
    """
    if not isinstance(window_title, str) or len(window_title) > 200:
        return {"error": "focus_window: title must be a string <= 200 chars"}
    if "\x00" in window_title or "`" in window_title:
        return {"error": "focus_window: title contains forbidden char"}
    script = r"""
Add-Type @"
  using System;
  using System.Runtime.InteropServices;
  public class Win32 {
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  }
"@
$needle = $env:VOODO_TITLE
# NOTE: don't name this $matches — that's a PowerShell automatic
# variable populated by any -match operator and can get clobbered.
$found = Get-Process | Where-Object { $_.MainWindowTitle -and $_.MainWindowTitle.Contains($needle) }
# Most-specific match wins: longest title containing the needle.
$ranked = $found | Sort-Object -Property @{Expression={$_.MainWindowTitle.Length}} -Descending
$pick   = $ranked | Select-Object -First 1
$result = @{}
$result["candidates"] = @($found | ForEach-Object { $_.MainWindowTitle } | Select-Object -Unique)
if ($pick) {
    [Win32]::ShowWindow($pick.MainWindowHandle, 9) | Out-Null  # SW_RESTORE
    [Win32]::SetForegroundWindow($pick.MainWindowHandle) | Out-Null
    $result["status"]  = "focused"
    $result["focused"] = $pick.MainWindowTitle
} else {
    $result["status"] = "not found"
}
$result | ConvertTo-Json -Compress
"""
    proc = _run_ps_internal(script, env={"VOODO_TITLE": window_title})
    import json as _json
    raw = (proc.stdout or "").strip()
    try:
        data = _json.loads(raw)
        if isinstance(data, dict):
            # Log to stdout so a stale-executor problem can be diagnosed
            # from the executor terminal: shows the needle, the chosen
            # title, and every candidate considered.
            print(
                f"[focus_window] needle={window_title!r} "
                f"-> {data.get('status')} {data.get('focused')!r} "
                f"(candidates: {data.get('candidates')!r})",
                flush=True,
            )
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"result": raw}


def minimize_all_windows() -> dict[str, Any]:
    script = "(New-Object -ComObject Shell.Application).MinimizeAll()"
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True)
    return {"status": "minimized"}


def get_system_info() -> dict[str, Any]:
    script = r"""
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average | Select-Object -ExpandProperty Average
    $ram_total = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
    $ram_free = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    @{ os=$os.Caption; cpu_percent=$cpu; ram_total_gb=$ram_total; ram_free_gb=$ram_free } | ConvertTo-Json
    """
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    import json
    try: return json.loads(proc.stdout)
    except: return {"raw": proc.stdout}


def set_volume(level: int, mute: bool = False) -> dict[str, Any]:
    """Set system volume via SendKeys. `level` is clamped to [0,100];
    `mute` is coerced to bool — so the script body is purely numeric
    interpolation and there is no string-injection surface."""
    try:
        lvl = max(0, min(int(level), 100))
    except (TypeError, ValueError):
        return {"error": "set_volume: level must be int"}
    mute_flag = bool(mute)
    mute_str = "$true" if mute_flag else "$false"
    # Numeric-only interpolation — safe.
    script = (
        "$obj = New-Object -ComObject WScript.Shell;"
        "for($i=0; $i -lt 50; $i++) { $obj.SendKeys([char]174) };"
        f"for($i=0; $i -lt ({lvl} / 2); $i++) {{ $obj.SendKeys([char]175) }};"
        f"if ({mute_str}) {{ $obj.SendKeys([char]173) }}"
    )
    _run_ps_internal(script)
    return {"level": lvl, "mute": mute_flag}


def get_audio_devices() -> dict[str, Any]:
    return {"status": "requires external module (AudioDeviceCmdlets), skipped in native implementation."}


def set_default_audio_device(device_name: str) -> dict[str, Any]:
    return {"status": "requires external module (AudioDeviceCmdlets), skipped in native implementation."}


def toggle_network(wifi: bool = True, bluetooth: bool = True) -> dict[str, Any]:
    """Enable/disable the Wi-Fi adapter. `wifi` / `bluetooth` are coerced
    to bool so the picked cmdlet name is one of two constants — no
    user-controlled string ever reaches the script body."""
    wifi_flag = bool(wifi)
    wifi_cmd = "Enable-NetAdapter" if wifi_flag else "Disable-NetAdapter"
    script = (
        f"Get-NetAdapter -Name 'Wi-Fi' -ErrorAction SilentlyContinue | "
        f"{wifi_cmd} -Confirm:$false"
    )
    _run_ps_internal(script)
    return {"wifi": wifi_flag, "bluetooth": bool(bluetooth)}


def check_network_status() -> dict[str, Any]:
    script = "Test-NetConnection -ComputerName 8.8.8.8 | Select-Object PingSucceeded | ConvertTo-Json"
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    return {"raw": proc.stdout.strip()}


def change_display_brightness(level: int) -> dict[str, Any]:
    """Set monitor brightness. `level` is coerced+clamped to [0,100] so
    the interpolation is numeric-only — no injection surface."""
    try:
        lvl = max(0, min(int(level), 100))
    except (TypeError, ValueError):
        return {"error": "change_display_brightness: level must be int"}
    script = (
        f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
        f".WmiSetBrightness(1, {lvl})"
    )
    _run_ps_internal(script)
    return {"brightness": lvl}


def read_clipboard() -> dict[str, Any]:
    """Read clipboard. The returned text is UNTRUSTED — the agent wraps
    it in an `untrusted` fence before showing the model."""
    proc = _run_ps_internal("Get-Clipboard")
    # Cap response size so a 10 MB clipboard can't blow up the prompt.
    return {"text": (proc.stdout or "").strip()[:2000]}


def write_clipboard(text: str) -> dict[str, Any]:
    """Write text to clipboard, passing the value via env so f-string
    quote-escapes don't apply."""
    try:
        validate_ps_arg(text, max_len=2000, allow_path=True)
    except ValueError as e:
        return {"error": f"write_clipboard: {e}"}
    script = "Set-Clipboard -Value $env:VOODO_CLIP"
    _run_ps_internal(script, env={"VOODO_CLIP": text})
    return {"status": "copied"}


def search_files(query: str, directory: str = ".") -> dict[str, Any]:
    """Recursive content search, restricted to the file allow-list.

    Args are passed through env vars — no string interpolation into the
    PS script body. Both `query` and `directory` are validated first.
    """
    if not isinstance(query, str) or len(query) > 200:
        return {"error": "search_files: query must be a string <= 200 chars"}
    if "`" in query or "\x00" in query:
        return {"error": "search_files: query contains forbidden char"}
    try:
        resolved_dir = validate_file_path(directory)
    except ValueError as e:
        return {"error": f"search_files: {e}"}
    # `-SimpleMatch` makes Select-String treat the pattern literally —
    # no regex injection. ConvertTo-Json is bounded.
    script = (
        "Get-ChildItem -Path $env:VOODO_DIR -Recurse -File "
        "-ErrorAction SilentlyContinue | "
        "Select-String -Pattern $env:VOODO_Q -SimpleMatch | "
        "Select-Object -First 50 Path, LineNumber, Line | "
        "ConvertTo-Json"
    )
    proc = _run_ps_internal(
        script,
        env={"VOODO_DIR": str(resolved_dir), "VOODO_Q": query},
        timeout=40,
    )
    import json
    try:
        return {"matches": json.loads(proc.stdout)}
    except Exception:  # noqa: BLE001
        return {"raw": (proc.stdout or "").strip()[:1000]}


def read_file_preview(file_path: str) -> dict[str, Any]:
    """Read up to 500 lines from a file inside the allow-list. Path is
    validated then passed via env var (never interpolated)."""
    try:
        resolved = validate_file_path(file_path)
    except ValueError as e:
        return {"error": f"read_file_preview: {e}"}
    script = "Get-Content -Path $env:VOODO_PATH -TotalCount 500 -ErrorAction SilentlyContinue | Out-String"
    proc = _run_ps_internal(script, env={"VOODO_PATH": str(resolved)})
    # Cap returned content so a 100MB log can't poison the prompt.
    return {"content": (proc.stdout or "").strip()[:4000], "path": str(resolved)}


def flush_dns() -> dict[str, Any]:
    """Clear the DNS resolver cache."""
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True, text=True)
    return {"status": "DNS cache flushed"}


def get_ip_info() -> dict[str, Any]:
    """Get IP address, gateway, and DNS servers."""
    import json as _json
    script = r"""
Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1 @{
    N='ip'; E={$_.IPv4Address.IPAddress}},
    @{N='gateway'; E={$_.IPv4DefaultGateway.NextHop}},
    @{N='dns'; E={($_.DNSServer.ServerAddresses) -join ', '}},
    @{N='interface'; E={$_.InterfaceAlias}
} | ConvertTo-Json
"""
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    try:
        return _json.loads(proc.stdout)
    except Exception:
        return {"raw": proc.stdout.strip()[:1000]}


def list_printers() -> dict[str, Any]:
    """List installed printers and default."""
    import json as _json
    script = r'Get-Printer | Select-Object Name, DriverName, PortName, Default | ConvertTo-Json'
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    try:
        data = _json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        return {"printers": data}
    except Exception:
        return {"raw": proc.stdout.strip()[:1000]}


def clear_print_queue() -> dict[str, Any]:
    """Stop the Print Spooler, clear the queue, restart it."""
    script = r"""
Stop-Service -Name Spooler -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:SystemRoot\System32\spool\PRINTERS\*" -Force -ErrorAction SilentlyContinue
Start-Service -Name Spooler
Get-Service Spooler | Select-Object Status | ConvertTo-Json
"""
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    return {"result": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def check_camera() -> dict[str, Any]:
    """Check camera devices and privacy permissions."""
    import json as _json
    script = r"""
$cam = Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -eq 'Camera' -or $_.PNPClass -eq 'Image' } | Select-Object Name, Status
$privacy = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam' -Name 'Value' -ErrorAction SilentlyContinue
@{
    cameras = $cam
    camera_privacy_access = if ($privacy) { $privacy.Value } else { 'unknown' }
} | ConvertTo-Json -Depth 3
"""
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    try:
        return _json.loads(proc.stdout)
    except Exception:
        return {"raw": proc.stdout.strip()[:1000]}


def list_usb_devices() -> dict[str, Any]:
    """List connected USB devices."""
    import json as _json
    script = r'Get-CimInstance Win32_USBControllerDevice | ForEach-Object { [wmi]($_.Dependent) } | Select-Object Name, Status, DeviceID | ConvertTo-Json'
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    try:
        data = _json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        return {"devices": data}
    except Exception:
        return {"raw": proc.stdout.strip()[:1000]}


def check_disk_space() -> dict[str, Any]:
    """Check total and free space for all drives."""
    import json as _json
    script = r"""
Get-CimInstance Win32_LogicalDisk | Where-Object DriveType -eq 3 | Select-Object DeviceID,
    @{N='SizeGB'; E={[math]::Round($_.Size / 1GB, 2)}},
    @{N='FreeGB'; E={[math]::Round($_.FreeSpace / 1GB, 2)}} | ConvertTo-Json
"""
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    try:
        data = _json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        return {"drives": data}
    except Exception:
        return {"raw": proc.stdout.strip()[:1000]}


def clear_temp_files() -> dict[str, Any]:
    """Delete *plain files only* inside %TEMP% and Windows Temp.

    SAFE BY CONSTRUCTION: we never descend into subdirectories, never
    call Remove-Item with -Recurse, and skip anything whose attributes
    include ReparsePoint. So even if an attacker process races a
    junction into existence between enumeration and deletion, the worst
    that can happen is one extra plain file inside %TEMP% gets deleted —
    we cannot escape %TEMP% because we never follow into directories.

    Trade-off: stale subdirectories under %TEMP% are not cleaned. That's
    acceptable; this is a "frees up some MB" diagnostic, not a full Disk
    Cleanup. Users who want deep cleaning should run `cleanmgr.exe`.
    """
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$deleted = 0
function Remove-FilesShallow($root) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { return 0 }
    $n = 0
    # -File restricts to plain files. We DO NOT recurse; we DO NOT touch
    # subdirectories at all. ReparsePoint attribute check is belt-and-
    # suspenders in case a file happens to be a hardlink/symlink.
    Get-ChildItem -LiteralPath $root -File -Force -ErrorAction SilentlyContinue |
        Where-Object { -not ($_.Attributes.ToString() -match 'ReparsePoint') } |
        ForEach-Object {
            try {
                Remove-Item -LiteralPath $_.FullName -Force `
                    -ErrorAction SilentlyContinue
                $script:n++
            } catch {}
        }
    return $n
}
$deleted += Remove-FilesShallow $env:TEMP
$deleted += Remove-FilesShallow "$env:SystemRoot\Temp"
"Deleted $deleted top-level temp files."
"""
    proc = _run_ps_internal(script, timeout=60)
    return {"status": (proc.stdout or "").strip() or "Temp files cleared."}


def get_event_log_errors() -> dict[str, Any]:
    """Get 10 recent errors from System and Application event logs."""
    import json as _json
    script = r"""
Get-WinEvent -FilterHashtable @{LogName='System','Application'; Level=2} -MaxEvents 10 -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id, ProviderName, Message | ConvertTo-Json
"""
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    try:
        data = _json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        return {"errors": data}
    except Exception:
        return {"raw": proc.stdout.strip()[:2000]}


def list_startup_programs() -> dict[str, Any]:
    """List applications configured to run at startup."""
    import json as _json
    script = r"""
Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location | ConvertTo-Json
"""
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True)
    try:
        data = _json.loads(proc.stdout)
        if isinstance(data, dict):
            data = [data]
        return {"startup_programs": data}
    except Exception:
        return {"raw": proc.stdout.strip()[:2000]}


def suggest_solution(suggestion: str) -> dict[str, Any]:
    # Like finish, this is an agent-side concept, but we add it here for dispatch table uniformity.
    return {"status": "suggested", "suggestion": suggestion}
def highlight_at(x: int, y: int, label: str = "", seconds: float = 4.0,
                 type_hint: str = "") -> dict[str, Any]:
    """Show the spotlight + comet-trail mouse guide at (x, y).

    Spawns client/scripts/mouse_guide.py as a detached subprocess. That script
    runs a fullscreen PyQt5 overlay (dark spotlight focused on the target,
    cyan trail behind the cursor, smooth animation) and exits when the
    user clicks or moves the mouse to the target. Falls back to the
    earlier inline tk ring if the script isn't found or PyQt5 isn't
    installed.

    `type_hint` (guide mode only): if non-empty, mouse_guide.py renders
    a small white bubble near the spotlight showing
        ⌨ Type: <type_hint>
    so the user sees what to type AFTER clicking the highlighted spot.
    Falls back to ignored if the mouse_guide.py path isn't taken.

    Non-blocking — returns immediately after launching the subprocess.
    """
    import pathlib
    import shutil
    import subprocess

    here = pathlib.Path(__file__).resolve().parent.parent
    guide = here / "scripts" / "mouse_guide.py"

    if guide.exists():
        # Prefer pythonw.exe on Windows so no console window flashes; fall
        # back to whatever python launched the executor.
        py = sys.executable
        if sys.platform == "win32":
            pyw = pathlib.Path(sys.executable).with_name("pythonw.exe")
            if pyw.exists():
                py = str(pyw)
        try:
            # Hard cap so the agent never blocks indefinitely on a user who
            # walks away. mouse_guide exits earlier when the user clicks or
            # moves the mouse — that's the common case.
            max_wait = max(float(seconds), 10.0)
            cmd = [py, str(guide), str(int(x)), str(int(y)),
                   "--timeout", f"{max_wait:.1f}"]
            if type_hint:
                # Cap to a sane width — the bubble grows with the text.
                cmd += ["--type-hint", str(type_hint)[:80]]
            if label:
                # Pass through `label` too — mouse_guide.py uses it as a
                # fallback source for the type-hint bubble when called
                # from an older agent that folded the hint into the
                # label arg (graceful-degrade path).
                cmd += ["--label", str(label)[:96]]
            proc = subprocess.Popen(
                cmd,
                cwd=str(here),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
            # BLOCK until the spotlight closes (user clicked / moved / timed out)
            # so the agent's next screenshot reflects what the user just did.
            try:
                proc.wait(timeout=max_wait + 5)
                exited = True
            except subprocess.TimeoutExpired:
                proc.kill()
                exited = False
            return {
                "shown": True, "x": x, "y": y, "label": label,
                "seconds": seconds, "via": "mouse_guide.py",
                "user_acted": exited,
            }
        except Exception as e:  # noqa: BLE001
            # Fall through to the tk fallback below if Popen failed (e.g.
            # PyQt5/pynput not installed in the executor's venv).
            print(f"[executor] highlight_at: mouse_guide.py launch failed: {e}", flush=True)

    # Fallback: minimal tk ring (no extra deps).
    import threading
    def _run() -> None:
        try:
            import tkinter as tk
        except ImportError:
            return
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", "black")
        except Exception:
            pass
        size = 200
        try:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        except Exception:
            sw = sh = 100000
        wx = max(0, min(int(x) - size // 2, sw - size))
        wy = max(0, min(int(y) - size // 2, sh - size))
        cx, cy = int(x) - wx, int(y) - wy
        root.geometry(f"{size}x{size}+{wx}+{wy}")
        canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_oval(cx - 60, cy - 60, cx + 60, cy + 60,
                           outline="#ff3b3b", width=6)
        canvas.create_line(cx - 14, cy, cx + 14, cy, fill="#ff3b3b", width=3)
        canvas.create_line(cx, cy - 14, cx, cy + 14, fill="#ff3b3b", width=3)
        root.after(int(seconds * 1000), root.destroy)
        try:
            root.mainloop()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
    return {"shown": True, "x": x, "y": y, "label": label,
            "seconds": seconds, "via": "tk-fallback"}


def finish(success: bool, summary: str) -> dict[str, Any]:
    # Executor never decides to finish; agent decides. This exists so the
    # dispatch table is uniform — calling it is a no-op acknowledgement.
    return {"success": bool(success), "summary": summary}


# ── Floating-assistant lifecycle ─────────────────────────────────────────
# Process handle for the running widget. Module-global so re-entrant calls
# can detect "already running" instead of spawning duplicates.
_assistant_proc: Any = None
import threading as _threading
_assistant_lock = _threading.Lock()


def open_assistant() -> dict[str, Any]:
    """Pop the floating voodo widget and minimize ALL windows.

    Called by the backend when a browser-side user starts (or resumes)
    a chat. Minimizing everything (Win+D-style MinimizeAll, not just
    the voo.do tab) gets the user's desktop into a clean state so the
    agent's next action — whatever app it opens or surface it touches —
    is the only thing on screen besides the floating widget itself.

    The widget has `Qt.WindowStaysOnTopHint`, so MinimizeAll does not
    hide it. Idempotent: re-firing while the widget is alive just
    re-minimizes.
    """
    global _assistant_proc
    import pathlib
    import tempfile

    launched = False
    with _assistant_lock:
        alive = _assistant_proc is not None and _assistant_proc.poll() is None
        if not alive:
            here = pathlib.Path(__file__).resolve().parent.parent
            script = here / "scripts" / "voodo_assistant.py"
            if not script.exists():
                return {"launched": False, "minimized": 0, "error": f"missing {script}"}
            log_path = pathlib.Path(tempfile.gettempdir()) / "voodo_assistant_stderr.log"
            log_fh = open(log_path, "ab", buffering=0)
            _assistant_proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(here),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdout=log_fh,
                stderr=log_fh,
                close_fds=True,
            )
            launched = True

    minimize_all_windows()
    return {"launched": launched, "minimized_all": True}


def _minimize_voodo_browser_tabs() -> int:
    """Minimize every top-level window whose title contains 'voo.do'
    (the browser-tab title set by app/static/index.html). Win32 only."""
    if sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes

    SW_MINIMIZE = 6
    user32 = ctypes.windll.user32
    count = [0]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "voo.do" in buf.value.lower():
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            count[0] += 1
        return True

    user32.EnumWindows(_cb, 0)
    return count[0]
