"""Schedules (what should happen when) and reminders (what has fired and awaits acknowledgement).

Schedules are only created through explicit requests (UI, desk client or an accepted tutor
plan). Delivery is a database row the desk polls; no model is involved.
"""

from __future__ import annotations

from typing import Annotated, Any

from companion_core.auth import ClientIdentity, Permission
from companion_worker.scheduler import Rule
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require

router = APIRouter(prefix="/v1")
Writer = Annotated[ClientIdentity, Depends(require(Permission.SCHEDULE_WRITE))]
Reader = Annotated[ClientIdentity, Depends(require(Permission.CONVERSE))]


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(default="reminder", pattern=r"^(reminder|lesson|review)$")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=2000)
    rule: Rule
    timezone: str | None = None
    missed_policy: str = Field(default="fire_late", pattern=r"^(fire_late|skip)$")
    grace_minutes: int = Field(default=120, ge=0, le=24 * 60)
    payload: dict[str, Any] = Field(default_factory=dict)


class Reschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: Rule
    timezone: str | None = None


class Snooze(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minutes: int = Field(default=10, ge=1, le=1440)


def _sched(request: Request) -> Any:
    return request.app.state.companion.scheduler


@router.get("/schedules")
async def list_schedules(identity: Reader, request: Request, status: str | None = None):
    return [s.model_dump() for s in _sched(request).list(client_id=identity.client_id, status=status.split(",") if status else None)]


@router.post("/schedules", status_code=201)
async def create_schedule(body: ScheduleCreate, identity: Writer, request: Request):
    st = request.app.state.companion
    return _sched(request).create(
        client_id=identity.client_id, kind=body.kind, title=body.title, rule=body.rule, timezone=body.timezone or st.config.instance.timezone,
        body=body.body, missed_policy=body.missed_policy, grace_minutes=body.grace_minutes, payload=body.payload,
    ).model_dump()


@router.post("/schedules/{schedule_id}/pause")
async def pause(schedule_id: str, identity: Writer, request: Request):
    _sched(request).get(schedule_id, client_id=identity.client_id)
    return _sched(request).set_status(schedule_id, "paused").model_dump()


@router.post("/schedules/{schedule_id}/resume")
async def resume(schedule_id: str, identity: Writer, request: Request):
    _sched(request).get(schedule_id, client_id=identity.client_id)
    return _sched(request).set_status(schedule_id, "active").model_dump()


@router.post("/schedules/{schedule_id}/cancel")
async def cancel(schedule_id: str, identity: Writer, request: Request):
    _sched(request).get(schedule_id, client_id=identity.client_id)
    return _sched(request).set_status(schedule_id, "cancelled").model_dump()


@router.post("/schedules/{schedule_id}/reschedule")
async def reschedule(schedule_id: str, body: Reschedule, identity: Writer, request: Request):
    _sched(request).get(schedule_id, client_id=identity.client_id)
    return _sched(request).reschedule(schedule_id, body.rule, timezone=body.timezone).model_dump()


@router.get("/reminders/pending")
async def pending(identity: Reader, request: Request):
    """What the desk should be showing or sounding right now."""
    return [r.model_dump() for r in _sched(request).pending(identity.client_id)]


@router.get("/reminders")
async def history(identity: Reader, request: Request, limit: int = 50):
    return [r.model_dump() for r in _sched(request).history(identity.client_id, limit=min(max(limit, 1), 200))]


@router.post("/reminders/{reminder_id}/ack")
async def ack(reminder_id: str, identity: Reader, request: Request):
    return _sched(request).acknowledge(reminder_id, client_id=identity.client_id).model_dump()


@router.post("/reminders/{reminder_id}/snooze")
async def snooze(reminder_id: str, body: Snooze, identity: Reader, request: Request):
    return _sched(request).snooze(reminder_id, body.minutes, client_id=identity.client_id).model_dump()


@router.post("/reminders/tick")
async def tick(identity: Annotated[ClientIdentity, Depends(require(Permission.ADMIN))], request: Request):
    """Admin/test helper: run the scheduler once (the worker does this every second normally)."""
    return [r.model_dump() for r in _sched(request).tick()]
