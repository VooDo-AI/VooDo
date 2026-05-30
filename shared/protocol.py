"""Wire types shared between the backend (server/) and the Windows
executor (client/executor/). This module is the protocol contract for
WebSocket payloads — changing it forces both sides to be redeployed.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

ToolName = Literal[
    "click",
    "double_click",
    "right_click",
    "type",
    "key",
    "hotkey",
    "scroll",
    "screenshot",
    "wait",
    "finish",
    "open_app",
    "close_app",
    "list_running_apps",
    "focus_window",
    "minimize_all_windows",
    "get_system_info",
    "set_volume",
    "get_audio_devices",
    "set_default_audio_device",
    "toggle_network",
    "check_network_status",
    "change_display_brightness",
    "read_clipboard",
    "write_clipboard",
    "search_files",
    "read_file_preview",
    "flush_dns",
    "get_ip_info",
    "list_printers",
    "clear_print_queue",
    "check_camera",
    "list_usb_devices",
    "suggest_solution",
    "highlight_at",
    "check_disk_space",
    "clear_temp_files",
    "get_event_log_errors",
    "list_startup_programs",
]

EventKind = Literal[
    "thought", "thought_delta",
    "tool_call", "observation", "result", "error", "status", "mode_change",
]


class UserMessage(BaseModel):
    """app -> agent. The user's description of their problem."""
    text: str
    attachments: list[str] = Field(default_factory=list)  # base64-encoded images


class ToolCall(BaseModel):
    """A single computer-use action the agent wants to take."""
    name: ToolName
    args: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    """agent -> app stream. One per loop step / status update."""
    kind: EventKind
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)


class ProblemQuery(BaseModel):
    """agent -> db. Lookup against the shared solutions DB."""
    description: str
    top_k: int = 3


class SolutionStep(BaseModel):
    action: ToolCall
    note: str | None = None


class SolutionRecord(BaseModel):
    """A successful (or attempted) fix the agent ran. Written back to DB on success."""
    id: str | None = None
    problem_summary: str
    steps: list[SolutionStep] = Field(default_factory=list)
    success: bool = True
    os: str = "windows"
    embedding: list[float] | None = None


class SolutionMatch(BaseModel):
    """db -> agent. A retrieved solution with its similarity score."""
    record: SolutionRecord
    score: float
