"""Persistent, timezone-aware schedules and reminders.

Rules are expressed in the user's local time (Europe/London by default) and resolved to UTC
instants with ``zoneinfo`` at each step, so the clocks changing in March and October are
handled: a 19:30 reminder stays at 19:30 local. Occurrences are de-duplicated by
(schedule, due_at); after downtime, ``fire_late`` delivers only the most recent missed
occurrence within the grace window and marks older ones missed, so a restart never causes an
alarm storm. Nothing here needs a language model.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from companion_core.clock import Clock, SystemClock, iso, parse_iso
from companion_core.db import Database
from companion_core.errors import Conflict, NotFound, ValidationFailed
from companion_core.ids import new_id
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["once", "daily", "weekly"]
    at_local: str | None = Field(default=None, description="once: YYYY-MM-DDTHH:MM in the schedule's timezone")
    time_local: str | None = Field(default=None, description="daily/weekly: HH:MM")
    days: list[int] | None = Field(default=None, description="weekly: 0=Monday .. 6=Sunday")
    until_local: str | None = Field(default=None, description="optional last date YYYY-MM-DD")

    @model_validator(mode="after")
    def _check(self) -> Rule:
        if self.type == "once":
            if not self.at_local:
                raise ValueError("once needs at_local")
            datetime.strptime(self.at_local, "%Y-%m-%dT%H:%M")
        else:
            if not self.time_local:
                raise ValueError(f"{self.type} needs time_local")
            time.fromisoformat(self.time_local)
            if self.type == "weekly":
                if not self.days or any(d < 0 or d > 6 for d in self.days):
                    raise ValueError("weekly needs days in 0..6")
        return self


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    client_id: str
    kind: str
    title: str
    body: str
    timezone: str
    rule: Rule
    next_run_at: str | None
    last_run_at: str | None
    status: Literal["active", "paused", "done", "cancelled"]
    missed_policy: Literal["fire_late", "skip"]
    grace_minutes: int
    payload: dict[str, Any]
    created_at: str
    updated_at: str


class Reminder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    schedule_id: str
    client_id: str
    due_at: str
    fired_at: str | None
    status: Literal["pending", "delivered", "acknowledged", "snoozed", "missed", "cancelled"]
    title: str
    body: str
    kind: str
    payload: dict[str, Any]
    acknowledged_at: str | None
    snoozed_until: str | None
    delivery_count: int
    created_at: str
    updated_at: str


def _local(dt_utc: datetime, tz: ZoneInfo) -> datetime:
    return dt_utc.astimezone(tz)


def _instant(local_date: Any, t: time, tz: ZoneInfo) -> datetime:
    """Local wall time -> UTC. Non-existent times (spring forward) resolve to the first valid
    instant after the gap; ambiguous times (autumn) take the first occurrence (fold=0)."""
    naive = datetime.combine(local_date, t)
    aware = naive.replace(tzinfo=tz, fold=0)
    # detect a gap: converting back does not round-trip
    if aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != naive:
        aware = (naive + timedelta(hours=1)).replace(tzinfo=tz, fold=1)
    return aware.astimezone(UTC)


def next_occurrence(rule: Rule, *, after: datetime, tz_name: str) -> datetime | None:
    """First occurrence strictly after ``after`` (UTC), or None when the rule is exhausted."""
    tz = ZoneInfo(tz_name)
    if rule.type == "once":
        inst = _instant(datetime.strptime(rule.at_local, "%Y-%m-%dT%H:%M").date(), datetime.strptime(rule.at_local, "%Y-%m-%dT%H:%M").time(), tz)  # type: ignore[arg-type]
        return inst if inst > after else None
    t = time.fromisoformat(rule.time_local)  # type: ignore[arg-type]
    until = datetime.strptime(rule.until_local, "%Y-%m-%d").date() if rule.until_local else None
    local_after = _local(after, tz)
    day = local_after.date()
    for _ in range(0, 400):
        if until and day > until:
            return None
        if rule.type == "daily" or (rule.days and day.weekday() in rule.days):
            inst = _instant(day, t, tz)
            if inst > after:
                return inst
        day += timedelta(days=1)
    return None


class SchedulerStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or SystemClock()

    def _now(self) -> datetime:
        return self.clock.now()

    @staticmethod
    def _schedule(r: Any) -> Schedule:
        return Schedule(
            id=r["id"], client_id=r["client_id"], kind=r["kind"], title=r["title"], body=r["body"], timezone=r["timezone"],
            rule=Rule.model_validate(json.loads(r["rule_json"])), next_run_at=r["next_run_at"], last_run_at=r["last_run_at"], status=r["status"],
            missed_policy=r["missed_policy"], grace_minutes=r["grace_minutes"], payload=json.loads(r["payload_json"]), created_at=r["created_at"], updated_at=r["updated_at"],
        )

    @staticmethod
    def _reminder(r: Any) -> Reminder:
        return Reminder(
            id=r["id"], schedule_id=r["schedule_id"], client_id=r["client_id"], due_at=r["due_at"], fired_at=r["fired_at"], status=r["status"], title=r["title"],
            body=r["body"], kind=r["kind"], payload=json.loads(r["payload_json"]), acknowledged_at=r["acknowledged_at"], snoozed_until=r["snoozed_until"],
            delivery_count=r["delivery_count"], created_at=r["created_at"], updated_at=r["updated_at"],
        )

    # -- schedules -------------------------------------------------------
    def create(self, *, client_id: str, kind: str, title: str, rule: Rule, timezone: str = "Europe/London", body: str = "",
               missed_policy: str = "fire_late", grace_minutes: int = 120, payload: dict[str, Any] | None = None) -> Schedule:
        try:
            ZoneInfo(timezone)
        except Exception as exc:  # noqa: BLE001
            raise ValidationFailed(f"unknown timezone {timezone!r}") from exc
        nxt = next_occurrence(rule, after=self._now(), tz_name=timezone)
        if nxt is None:
            raise ValidationFailed("the rule has no future occurrence")
        now = iso(self._now())
        sid = new_id("sch")
        self.db.execute(
            "INSERT INTO schedules(id, client_id, kind, title, body, timezone, rule_json, next_run_at, status, missed_policy, grace_minutes, payload_json, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,'active',?,?,?,?,?)",
            (sid, client_id, kind, title[:200], body[:2000], timezone, rule.model_dump_json(exclude_none=True), iso(nxt), missed_policy, grace_minutes, json.dumps(payload or {}), now, now),
        )
        return self.get(sid)

    def get(self, schedule_id: str, *, client_id: str | None = None) -> Schedule:
        row = self.db.query_one("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        if not row or (client_id is not None and row["client_id"] != client_id):
            raise NotFound(f"schedule {schedule_id} not found")
        return self._schedule(row)

    def list(self, *, client_id: str | None = None, status: list[str] | None = None, kind: str | None = None) -> list[Schedule]:
        sql = "SELECT * FROM schedules WHERE 1=1"
        params: list[Any] = []
        if client_id is not None:
            sql += " AND client_id = ?"
            params.append(client_id)
        if status:
            sql += f" AND status IN ({','.join('?' * len(status))})"
            params += status
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY COALESCE(next_run_at, '9999') ASC"
        return [self._schedule(r) for r in self.db.query(sql, tuple(params))]

    def set_status(self, schedule_id: str, status: str) -> Schedule:
        sch = self.get(schedule_id)
        if sch.status in {"done", "cancelled"} and status != sch.status:
            raise Conflict(f"schedule is {sch.status}")
        now = self._now()
        if status == "active" and sch.status == "paused":
            nxt = next_occurrence(sch.rule, after=now, tz_name=sch.timezone)
            self.db.execute("UPDATE schedules SET status = 'active', next_run_at = ?, updated_at = ? WHERE id = ?", (iso(nxt) if nxt else None, iso(now), schedule_id))
        else:
            self.db.execute("UPDATE schedules SET status = ?, updated_at = ? WHERE id = ?", (status, iso(now), schedule_id))
        return self.get(schedule_id)

    def reschedule(self, schedule_id: str, rule: Rule, *, timezone: str | None = None) -> Schedule:
        sch = self.get(schedule_id)
        tz = timezone or sch.timezone
        nxt = next_occurrence(rule, after=self._now(), tz_name=tz)
        if nxt is None:
            raise ValidationFailed("the new rule has no future occurrence")
        self.db.execute("UPDATE schedules SET rule_json = ?, timezone = ?, next_run_at = ?, status = 'active', updated_at = ? WHERE id = ?",
                        (rule.model_dump_json(exclude_none=True), tz, iso(nxt), iso(self._now()), schedule_id))
        return self.get(schedule_id)

    # -- firing ----------------------------------------------------------
    def tick(self) -> list[Reminder]:
        """Create and deliver due occurrences. Safe to call as often as you like."""
        now = self._now()
        fired: list[Reminder] = []
        due = self.db.query("SELECT * FROM schedules WHERE status = 'active' AND next_run_at IS NOT NULL AND next_run_at <= ? ORDER BY next_run_at", (iso(now),))
        for row in due:
            sch = self._schedule(row)
            occurrences: list[datetime] = []
            cursor = parse_iso(sch.next_run_at)  # type: ignore[arg-type]
            while cursor is not None and cursor <= now and len(occurrences) < 1000:
                occurrences.append(cursor)
                cursor = next_occurrence(sch.rule, after=cursor, tz_name=sch.timezone)
            grace = timedelta(minutes=sch.grace_minutes)
            latest = occurrences[-1]
            for occ in occurrences:
                is_latest = occ == latest
                beyond_grace = now - occ > grace
                delayed = now - occ > timedelta(minutes=5)
                if is_latest and not (beyond_grace and sch.missed_policy == "skip"):
                    r = self._fire(sch, occ, now, late=delayed)
                    if r is not None:
                        fired.append(r)
                else:
                    self._record(sch, occ, now, status="missed")
            with self.db.transaction() as conn:
                if cursor is None:
                    conn.execute("UPDATE schedules SET next_run_at = NULL, status = 'done', last_run_at = ?, updated_at = ? WHERE id = ?", (iso(latest), iso(now), sch.id))
                else:
                    conn.execute("UPDATE schedules SET next_run_at = ?, last_run_at = ?, updated_at = ? WHERE id = ?", (iso(cursor), iso(latest), iso(now), sch.id))
        # re-deliver snoozed reminders whose snooze has ended
        for row in self.db.query("SELECT * FROM reminders WHERE status = 'snoozed' AND snoozed_until <= ?", (iso(now),)):
            self.db.execute("UPDATE reminders SET status = 'delivered', fired_at = ?, delivery_count = delivery_count + 1, snoozed_until = NULL, updated_at = ? WHERE id = ?", (iso(now), iso(now), row["id"]))
            fired.append(self.get_reminder(row["id"]))
        return fired

    def _record(self, sch: Schedule, occ: datetime, now: datetime, *, status: str) -> str | None:
        rid = new_id("rem")
        cur = self.db.execute(
            "INSERT OR IGNORE INTO reminders(id, schedule_id, client_id, due_at, status, title, body, kind, payload_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rid, sch.id, sch.client_id, iso(occ), status, sch.title, sch.body, sch.kind, json.dumps(sch.payload), iso(now), iso(now)),
        )
        return rid if cur.rowcount == 1 else None

    def _fire(self, sch: Schedule, occ: datetime, now: datetime, *, late: bool) -> Reminder | None:
        rid = self._record(sch, occ, now, status="pending")
        if rid is None:
            return None  # already created by an earlier tick: never a duplicate alarm
        body = sch.body + (f"\n(Delivered late: this was due at {occ.astimezone(ZoneInfo(sch.timezone)).strftime('%H:%M on %A')}.)" if late else "")
        self.db.execute("UPDATE reminders SET status = 'delivered', fired_at = ?, delivery_count = 1, body = ?, updated_at = ? WHERE id = ?", (iso(now), body.strip(), iso(now), rid))
        return self.get_reminder(rid)

    # -- reminders -------------------------------------------------------
    def get_reminder(self, reminder_id: str, *, client_id: str | None = None) -> Reminder:
        row = self.db.query_one("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        if not row or (client_id is not None and row["client_id"] != client_id):
            raise NotFound(f"reminder {reminder_id} not found")
        return self._reminder(row)

    def pending(self, client_id: str) -> list[Reminder]:
        """Delivered but not yet acknowledged: what the desk should be showing/sounding."""
        rows = self.db.query("SELECT * FROM reminders WHERE client_id = ? AND status = 'delivered' ORDER BY due_at", (client_id,))
        return [self._reminder(r) for r in rows]

    def history(self, client_id: str, *, limit: int = 50) -> list[Reminder]:
        rows = self.db.query("SELECT * FROM reminders WHERE client_id = ? ORDER BY due_at DESC LIMIT ?", (client_id, limit))
        return [self._reminder(r) for r in rows]

    def acknowledge(self, reminder_id: str, *, client_id: str | None = None) -> Reminder:
        rem = self.get_reminder(reminder_id, client_id=client_id)
        if rem.status not in {"delivered", "snoozed"}:
            raise Conflict(f"reminder is {rem.status}")
        now = iso(self._now())
        self.db.execute("UPDATE reminders SET status = 'acknowledged', acknowledged_at = ?, updated_at = ? WHERE id = ?", (now, now, reminder_id))
        return self.get_reminder(reminder_id)

    def snooze(self, reminder_id: str, minutes: int, *, client_id: str | None = None) -> Reminder:
        if not 1 <= minutes <= 24 * 60:
            raise ValidationFailed("snooze between 1 minute and 24 hours")
        rem = self.get_reminder(reminder_id, client_id=client_id)
        if rem.status != "delivered":
            raise Conflict(f"reminder is {rem.status}")
        until = self._now() + timedelta(minutes=minutes)
        self.db.execute("UPDATE reminders SET status = 'snoozed', snoozed_until = ?, updated_at = ? WHERE id = ?", (iso(until), iso(self._now()), reminder_id))
        return self.get_reminder(reminder_id)
