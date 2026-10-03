from __future__ import annotations

from typing import Protocol

from companion_contracts.health import DependencyStatus
from pydantic import BaseModel, ConfigDict, Field


class EmailMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    thread_id: str | None = None
    subject: str = ""
    sender: str = ""
    to: str = ""
    date: str | None = None  # ISO 8601 UTC
    snippet: str = ""
    body_text: str = ""
    labels: list[str] = Field(default_factory=list)
    link: str | None = None
    provider: str = ""
    is_fixture: bool = False


class EmailSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    messages: list[EmailMessage] = Field(default_factory=list)
    next_page_token: str | None = None
    result_size_estimate: int | None = None
    provider: str
    is_fixture: bool = False
    account_label: str = ""


class EmailProvider(Protocol):
    name: str
    is_fixture: bool
    account_label: str

    async def search(self, query: str, *, limit: int = 10, page_token: str | None = None) -> EmailSearchResult: ...
    async def get(self, message_id: str) -> EmailMessage: ...
    async def health(self) -> DependencyStatus: ...
