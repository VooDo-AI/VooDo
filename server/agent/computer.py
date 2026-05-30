"""Remote computer module — proxies tool calls to the Windows executor.

The agent runs on the backend; the user's screen is on a different machine.
Each function here is a sync call into the in-process ExecutorBridge, which
forwards the call over the long-lived WebSocket that the Windows executor
opened to us.
"""
from __future__ import annotations

from typing import Any

from server.app.bridge import bridge


class ClientComputer:
    def __init__(self, client_id: str):
        self.client_id = client_id

    def _call(self, name: str, args: dict[str, Any] | None = None, timeout: float = 60.0) -> dict[str, Any]:
        return bridge.call_sync(self.client_id, name, args or {}, timeout=timeout)

    def screenshot(self) -> dict[str, Any]:
        return self._call("screenshot")

    def click(self, x: int, y: int) -> dict[str, Any]:
        return self._call("click", {"x": x, "y": y})

    def double_click(self, x: int, y: int) -> dict[str, Any]:
        return self._call("double_click", {"x": x, "y": y})

    def right_click(self, x: int, y: int) -> dict[str, Any]:
        return self._call("right_click", {"x": x, "y": y})

    def type(self, text: str) -> dict[str, Any]:  # noqa: A001
        return self._call("type", {"text": text})

    def key(self, key: str) -> dict[str, Any]:  # noqa: A002
        return self._call("key", {"key": key})

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        return self._call("hotkey", {"keys": keys})

    def scroll(self, amount: int) -> dict[str, Any]:
        return self._call("scroll", {"amount": amount})

    def wait(self, seconds: float) -> dict[str, Any]:
        return self._call("wait", {"seconds": seconds}, timeout=float(seconds) + 5.0)

    def open_app(self, app_name: str) -> dict[str, Any]:
        return self._call("open_app", {"app_name": app_name})

    def close_app(self, app_name: str) -> dict[str, Any]:
        return self._call("close_app", {"app_name": app_name})

    def list_running_apps(self) -> dict[str, Any]:
        return self._call("list_running_apps")

    def focus_window(self, window_title: str) -> dict[str, Any]:
        return self._call("focus_window", {"window_title": window_title})

    def minimize_all_windows(self) -> dict[str, Any]:
        return self._call("minimize_all_windows")

    def get_system_info(self) -> dict[str, Any]:
        return self._call("get_system_info")

    def set_volume(self, level: int, mute: bool = False) -> dict[str, Any]:
        return self._call("set_volume", {"level": level, "mute": mute})

    def get_audio_devices(self) -> dict[str, Any]:
        return self._call("get_audio_devices")

    def set_default_audio_device(self, device_name: str) -> dict[str, Any]:
        return self._call("set_default_audio_device", {"device_name": device_name})

    def toggle_network(self, wifi: bool = True, bluetooth: bool = True) -> dict[str, Any]:
        return self._call("toggle_network", {"wifi": wifi, "bluetooth": bluetooth}, timeout=20.0)

    def check_network_status(self) -> dict[str, Any]:
        return self._call("check_network_status")

    def change_display_brightness(self, level: int) -> dict[str, Any]:
        return self._call("change_display_brightness", {"level": level})

    def read_clipboard(self) -> dict[str, Any]:
        return self._call("read_clipboard")

    def write_clipboard(self, text: str) -> dict[str, Any]:
        return self._call("write_clipboard", {"text": text})

    def search_files(self, query: str, directory: str = ".") -> dict[str, Any]:
        return self._call("search_files", {"query": query, "directory": directory}, timeout=40.0)

    def read_file_preview(self, file_path: str) -> dict[str, Any]:
        return self._call("read_file_preview", {"file_path": file_path})

    def flush_dns(self) -> dict[str, Any]:
        return self._call("flush_dns")

    def get_ip_info(self) -> dict[str, Any]:
        return self._call("get_ip_info")

    def list_printers(self) -> dict[str, Any]:
        return self._call("list_printers")

    def clear_print_queue(self) -> dict[str, Any]:
        return self._call("clear_print_queue", timeout=15.0)

    def check_camera(self) -> dict[str, Any]:
        return self._call("check_camera")

    def list_usb_devices(self) -> dict[str, Any]:
        return self._call("list_usb_devices")

    def check_disk_space(self) -> dict[str, Any]:
        return self._call("check_disk_space")

    def clear_temp_files(self) -> dict[str, Any]:
        return self._call("clear_temp_files", timeout=60.0)

    def get_event_log_errors(self) -> dict[str, Any]:
        return self._call("get_event_log_errors")

    def list_startup_programs(self) -> dict[str, Any]:
        return self._call("list_startup_programs")

    def suggest_solution(self, suggestion: str) -> dict[str, Any]:
        return {"status": "suggested", "suggestion": suggestion}

    def highlight_at(self, x: int, y: int, label: str = "", seconds: float = 4.0,
                     type_hint: str = "") -> dict[str, Any]:
        args: dict[str, Any] = {"x": x, "y": y, "label": label, "seconds": seconds}
        if type_hint:
            args["type_hint"] = type_hint
        return self._call("highlight_at", args, timeout=60.0)

    def finish(self, success: bool, summary: str) -> dict[str, Any]:
        return {"success": bool(success), "summary": summary}
