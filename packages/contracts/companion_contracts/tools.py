"""Typed tool contracts.

A ``ToolSpec`` is what the gateway advertises to a model (JSON schema generated from
the argument model) and what it validates calls against. Permission and resource
checks happen in the gateway, never in the prompt.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Source

RiskLevel = Literal["read", "write", "actuate"]


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    permission: str
    risk: RiskLevel = "read"
    parameters: dict[str, Any]  # JSON schema
    requires_confirmation: bool = False
    provider: str | None = None
    enabled: bool = True
    disabled_reason: str | None = None

    def to_ollama(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class ToolResult(BaseModel):
    """What a tool hands back. ``content`` is what the model sees (untrusted-wrapped later)."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    content: str
    summary: str = ""
    sources: list[Source] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    ui_events: list[dict[str, Any]] = Field(default_factory=list)
    provider: str | None = None
    is_fixture: bool = False
    error_code: str | None = None


# ---- argument models (one per tool) -------------------------------------------------


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemorySearchArgs(_Args):
    query: str = Field(min_length=1, max_length=500, description="Keywords describing what to find")
    limit: int = Field(default=5, ge=1, le=20)
    kinds: list[str] | None = Field(default=None, description="Restrict to record kinds, e.g. ['note','meeting_summary']")


class MemorySaveArgs(_Args):
    text: str = Field(min_length=1, max_length=20000, description="Exactly what the user asked to remember")
    title: str = Field(default="", max_length=200)
    kind: Literal["note", "decision", "fact", "action"] = "note"
    project: str | None = Field(default=None, max_length=120)


class MemoryCorrectArgs(_Args):
    document_id: str = Field(description="The record being corrected")
    new_text: str = Field(min_length=1, max_length=20000)
    reason: str = Field(default="", max_length=500)


class FactRememberArgs(_Args):
    subject: str = Field(default="owner", min_length=1, max_length=120, description="Who or what the fact is about; 'owner' for the user")
    predicate: str = Field(min_length=1, max_length=120, description="e.g. 'favourite tea', 'timezone', 'bike lock code location'")
    value: str = Field(min_length=1, max_length=2000)
    note: str | None = Field(default=None, max_length=300)


class DecisionRecordArgs(_Args):
    statement: str = Field(min_length=1, max_length=4000)
    project: str | None = Field(default=None, max_length=120)
    rationale: str | None = Field(default=None, max_length=4000)
    supersedes_decision_id: str | None = Field(default=None, description="Set when this replaces an earlier decision")


class ClockNowArgs(_Args):
    pass


class HomeControlArgs(_Args):
    entity_id: str = Field(pattern=r"^[a-z_]+\.[a-z0-9_]+$")
    action: Literal["turn_on", "turn_off", "toggle", "activate"]
    brightness_pct: int | None = Field(default=None, ge=0, le=100)
    color_temp_kelvin: int | None = Field(default=None, ge=1000, le=10000)
    rgb_color: list[int] | None = Field(default=None, min_length=3, max_length=3)


class HomeStateArgs(_Args):
    entity_id: str | None = Field(default=None, pattern=r"^[a-z_]+\.[a-z0-9_]+$")
    domain: str | None = Field(default=None, pattern=r"^[a-z_]+$")


class CameraShowArgs(_Args):
    camera: str = Field(description="Camera friendly name or entity id, e.g. 'front door' or camera.front_door")


class WeatherArgs(_Args):
    day: Literal["today", "tomorrow", "week"] = "today"


class MathsArgs(_Args):
    expression: str = Field(min_length=1, max_length=400, description="An expression or equation, e.g. '2*x + 3 = 11'")
    task: Literal["evaluate", "simplify", "solve", "differentiate", "integrate", "explain"] = "evaluate"
    variable: str | None = Field(default=None, pattern=r"^[a-zA-Z]$")


class EmailSearchArgs(_Args):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=50)


class OrdersSearchArgs(_Args):
    merchant: str | None = Field(default=None, max_length=80)
    days: int = Field(default=90, ge=1, le=730)


class DeckCardCheckArgs(_Args):
    deck: str = Field(description="Saved deck name")
    card: str = Field(min_length=1, max_length=150)


class MeetingStartArgs(_Args):
    title: str = Field(default="", max_length=200)
    participants_informed: bool = Field(description="The user confirms participants know recording is on")


class MeetingControlArgs(_Args):
    action: Literal["pause", "resume", "stop"]


class MeetingQueryArgs(_Args):
    query: str = Field(min_length=1, max_length=300)
    meeting: str | None = Field(default=None, max_length=200)


class TutorArgs(_Args):
    action: Literal["status", "next_lesson", "propose_course", "start_lesson", "review"]
    topic: str | None = Field(default=None, max_length=120)
    goal: str | None = Field(default=None, max_length=500)


class RobotCommandArgs(_Args):
    action: Literal["stop", "look", "move", "turn", "dock", "status"]
    direction: Literal["forward", "backward", "left", "right", "up", "down", "centre"] | None = None
    distance_m: float | None = Field(default=None, ge=0, le=2.0)
    angle_deg: float | None = Field(default=None, ge=-180, le=180)
    duration_s: float | None = Field(default=None, gt=0, le=5.0)


__all__ = [name for name in dir() if name.endswith("Args") or name in {"ToolSpec", "ToolResult", "Source"}]
