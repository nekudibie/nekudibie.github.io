"""Shared value types: provenance, anchors and citations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal[
    "note",
    "document",
    "meeting_transcript",
    "meeting_summary",
    "email",
    "camera_ocr",
    "web",
    "tool_result",
    "conversation",
    "manual",
]


class Anchor(BaseModel):
    """A stable pointer into a source so a citation can be re-opened later."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["offset", "page", "segment", "message", "paragraph"] = "offset"
    start: int | None = None
    end: int | None = None
    page: int | None = None
    segment_id: str | None = None
    message_id: str | None = None
    paragraph: int | None = None
    start_time_s: float | None = None
    end_time_s: float | None = None


class Provenance(BaseModel):
    """Where a record came from. Every stored record carries one."""

    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    source_ref: str = Field(default="", description="Stable id in the source system (message id, file hash, job id)")
    source_uri: str | None = Field(default=None, description="Accessible link where one exists")
    captured_by: str = Field(default="", description="client id or service that captured it")
    captured_at: str | None = None
    trust: Literal["owner_stated", "imported", "inferred"] = "imported"


class Source(BaseModel):
    """A citation returned with an answer. ``label`` is what the UI shows ([S1], [S2] ...)."""

    model_config = ConfigDict(extra="forbid")

    label: str
    document_id: str
    chunk_id: str | None = None
    title: str
    snippet: str
    source_type: SourceType
    anchor: Anchor | None = None
    source_uri: str | None = None
    captured_at: str | None = None
    score: float | None = None
    provider: str = "vault"


class UntrustedText(BaseModel):
    """Content that must never be treated as instructions (emails, notes, OCR, tool output)."""

    text: str
    origin: str
    source_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
