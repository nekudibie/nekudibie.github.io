"""Memory vault request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Anchor, Provenance, Source

DocumentKind = Literal[
    "note", "decision", "fact", "action", "document", "meeting_transcript", "meeting_summary", "email", "lesson_note"
]
Scope = Literal["owner", "shared", "private"]


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: DocumentKind
    title: str
    text: str | None = None
    mime_type: str = "text/plain"
    scope: Scope = "owner"
    project: str | None = None
    provenance: Provenance
    content_sha256: str
    revision: int = 1
    supersedes_id: str | None = None
    superseded_by_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    deleted_at: str | None = None


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document_id: str
    seq: int
    text: str
    anchor: Anchor


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=50000)
    title: str = Field(default="", max_length=200)
    kind: DocumentKind = "note"
    scope: Scope = "owner"
    project: str | None = Field(default=None, max_length=120)
    provenance: Provenance | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=300)
    text: str = Field(min_length=1)
    kind: DocumentKind = "document"
    mime_type: str = "text/plain"
    scope: Scope = "owner"
    project: str | None = None
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, description="Same key + same content = same document")


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_text: str = Field(min_length=1, max_length=50000)
    reason: str = Field(default="", max_length=500)
    title: str | None = None


def _default_scopes() -> list[Scope]:
    return ["owner", "shared"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=50)
    kinds: list[DocumentKind] | None = None
    scopes: list[Scope] = Field(default_factory=_default_scopes)
    project: str | None = None
    include_superseded: bool = False
    since: str | None = Field(default=None, description="ISO timestamp lower bound on created_at")


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    chunk_id: str
    title: str
    kind: DocumentKind
    snippet: str
    text: str
    score: float
    anchor: Anchor
    provenance: Provenance
    created_at: str
    revision: int
    is_current: bool

    def to_source(self, label: str) -> Source:
        return Source(
            label=label,
            document_id=self.document_id,
            chunk_id=self.chunk_id,
            title=self.title,
            snippet=self.snippet,
            source_type=self.provenance.source_type,
            anchor=self.anchor,
            source_uri=self.provenance.source_uri,
            captured_at=self.created_at,
            score=self.score,
        )


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[SearchHit]
    total_candidates: int
    strategy: str


class DeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    deleted: bool
    chunks_removed: int
    note: str
