"""Streamed UI events sent over Server-Sent Events while a turn is processed.

The desk UI and the audio client key their state machine off these. Keep the
set small and explicit; add a new event rather than overloading an existing one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Source

AssistantState = Literal[
    "idle",
    "listening",
    "transcribing",
    "thinking",
    "tool_running",
    "speaking",
    "muted",
    "recording",
    "offline",
    "error",
]


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StateEvent(_Event):
    type: Literal["state"] = "state"
    state: AssistantState
    detail: str | None = None


class TokenEvent(_Event):
    type: Literal["token"] = "token"
    text: str


class ToolCallEvent(_Event):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["validated", "invalid", "denied", "unknown_tool"]
    reason: str | None = None


class ToolResultEvent(_Event):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    name: str
    ok: bool
    summary: str
    provider: str | None = None
    is_fixture: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class UIEvent(_Event):
    """An explicit instruction for the interface (show a camera, open a panel)."""

    type: Literal["ui"] = "ui"
    action: Literal["show_camera", "open_panel", "show_sources", "set_recording_indicator", "notify"]
    payload: dict[str, Any] = Field(default_factory=dict)


class SourcesEvent(_Event):
    type: Literal["sources"] = "sources"
    sources: list[Source]


class DoneEvent(_Event):
    type: Literal["done"] = "done"
    message_id: str
    route: Literal["deterministic", "llm", "fixture_llm"]
    model: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int


class ErrorEvent(_Event):
    type: Literal["error"] = "error"
    code: str
    message: str
    recoverable: bool = True


StreamEvent = (
    StateEvent | TokenEvent | ToolCallEvent | ToolResultEvent | UIEvent | SourcesEvent | DoneEvent | ErrorEvent
)
