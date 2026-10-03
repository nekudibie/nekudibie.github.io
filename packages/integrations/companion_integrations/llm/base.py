from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

from companion_contracts.health import DependencyStatus
from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    arguments: Any = Field(default_factory=dict)  # dict normally; models sometimes emit a JSON string


class LLMChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    done: bool = False
    done_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str
    is_fixture: bool

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[LLMChunk]: ...

    async def health(self) -> DependencyStatus: ...
