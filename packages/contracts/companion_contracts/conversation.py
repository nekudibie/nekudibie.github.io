"""Conversation and message records."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Source

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    role: Role
    content: str
    tool_name: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    client_id: str
    title: str
    state: Literal["active", "archived"] = "active"
    created_at: str
    updated_at: str
    message_count: int = 0


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=200)


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=20000)
    input_mode: Literal["text", "voice"] = "text"
    # The client may say which UI it has so tools can emit matching UI events.
    client_capabilities: list[str] = Field(default_factory=list)
