"""Health, readiness and version payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DependencyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["ok", "degraded", "down", "disabled", "fixture"]
    detail: str = ""
    latency_ms: int | None = None


class Readiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    service: str
    dependencies: list[DependencyStatus] = Field(default_factory=list)
    checked_at: str
