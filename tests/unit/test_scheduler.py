from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from companion_api.store import ConversationStore
from companion_core.clock import FakeClock, parse_iso
from companion_core.db import Database
from companion_core.errors import Conflict, ValidationFailed
from companion_worker.scheduler import Rule, SchedulerStore, next_occurrence

LONDON = ZoneInfo("Europe/London")


def utc(y, m, d, hh=0, mm=0):  # type: ignore[no-untyped-def]
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


@pytest.fixture
def clock():
    return FakeClock(utc(2026, 10, 23, 12, 0))  # Friday, BST still in force (clocks go back 25 Oct 2026)


@pytest.fixture
def store(tmp_path, clock):
    db = Database(tmp_path / "brain.db")
    ConversationStore(db).migrate()
    return SchedulerStore(db, clock)


def test_daily_rule_keeps_local_time_across_autumn_clock_change():
    rule = Rule(type="daily", time_local="19:30")
    a = next_occurrence(rule, after=utc(2026, 10, 24, 12), tz_name="Europe/London")
    b = next_occurrence(rule, after=a, tz_name="Europe/London")
    assert a == utc(2026, 10, 24, 18, 30)  # 19:30 BST
    assert b == utc(2026, 10, 25, 19, 30)  # 19:30 GMT: 25 hours later in UTC, same wall clock
    assert a.astimezone(LONDON).strftime("%H:%M") == b.astimezone(LONDON).strftime("%H:%M") == "19:30"


def test_spring_forward_gap_fires_once_at_first_valid_instant():
    rule = Rule(type="daily", time_local="01:30")  # 01:30 does not exist on 29 March 2026
    before = next_occurrence(rule, after=utc(2026, 3, 28, 12), tz_name="Europe/London")
    gap = next_occurrence(rule, after=before, tz_name="Europe/London")
    after_gap = next_occurrence(rule, after=gap, tz_name="Europe/London")
    assert before == utc(2026, 3, 29, 1, 30)  # 01:30 GMT on the 29th... which is the gap day's instant
    assert gap == utc(2026, 3, 30, 0, 30)  # 01:30 BST on the 30th
    assert after_gap == utc(2026, 3, 31, 0, 30)
    assert gap - before < (after_gap - gap) + (after_gap - gap)  # no occurrence was skipped or doubled


def test_weekly_and_once_rules():
    weekly = Rule(type="weekly", days=[0, 2, 4], time_local="08:00")  # Mon/Wed/Fri
    nxt = next_occurrence(weekly, after=utc(2026, 10, 23, 12), tz_name="Europe/London")  # Friday noon -> Monday
    assert nxt.astimezone(LONDON).strftime("%A %H:%M") == "Monday 08:00"
    once = Rule(type="once", at_local="2026-12-25T09:00")
    assert next_occurrence(once, after=utc(2026, 10, 1), tz_name="Europe/London") == utc(2026, 12, 25, 9, 0)
    assert next_occurrence(once, after=utc(2026, 12, 26), tz_name="Europe/London") is None
    with pytest.raises(ValueError):
        Rule(type="weekly", time_local="08:00", days=[7])
    with pytest.raises(ValueError):
        Rule(type="once")


def test_tick_fires_once_and_never_duplicates(store, clock):
    sch = store.create(client_id="desk", kind="reminder", title="Python lesson", rule=Rule(type="daily", time_local="19:30"))
    assert parse_iso(sch.next_run_at) == utc(2026, 10, 23, 18, 30)
    assert store.tick() == []
    clock.set(utc(2026, 10, 23, 18, 31))
    fired = store.tick()
    assert len(fired) == 1 and fired[0].status == "delivered" and fired[0].title == "Python lesson"
    assert store.tick() == [] and store.tick() == []  # repeated ticks: no second alarm
    assert [r.id for r in store.pending("desk")] == [fired[0].id]
    nxt = store.get(sch.id)
    assert parse_iso(nxt.next_run_at) == utc(2026, 10, 24, 18, 30) and parse_iso(nxt.last_run_at) == utc(2026, 10, 23, 18, 30)


def test_restart_recovery_overdue_within_grace_fires_late(store, clock):
    store.create(client_id="desk", kind="reminder", title="Stretch", rule=Rule(type="daily", time_local="14:00"), grace_minutes=120)
    clock.set(utc(2026, 10, 23, 13, 0 + 45))  # 14:45 BST: 45 minutes late (e.g. after a reboot)
    fired = store.tick()
    assert len(fired) == 1 and "Delivered late" in fired[0].body
    assert store.history("desk")[0].status == "delivered"


def test_restart_recovery_beyond_grace_with_skip_policy_marks_missed(store, clock):
    store.create(client_id="desk", kind="reminder", title="Water plants", rule=Rule(type="daily", time_local="14:00"), grace_minutes=60, missed_policy="skip")
    clock.set(utc(2026, 10, 23, 16, 0))  # 17:00 BST, 3 hours late
    assert store.tick() == []
    hist = store.history("desk")
    assert len(hist) == 1 and hist[0].status == "missed"
    assert store.pending("desk") == []


def test_long_downtime_fires_only_latest_occurrence(store, clock):
    store.create(client_id="desk", kind="reminder", title="Daily", rule=Rule(type="daily", time_local="09:00"), grace_minutes=24 * 60)
    clock.set(utc(2026, 10, 27, 9, 30))  # four days later (and across the clock change)
    fired = store.tick()
    assert len(fired) == 1 and parse_iso(fired[0].due_at) == utc(2026, 10, 27, 9, 0)
    statuses = sorted(r.status for r in store.history("desk"))
    assert statuses == ["delivered", "missed", "missed", "missed"]


def test_acknowledge_and_snooze(store, clock):
    store.create(client_id="desk", kind="reminder", title="Call Sam", rule=Rule(type="once", at_local="2026-10-23T15:00"))
    clock.set(utc(2026, 10, 23, 14, 0))
    (rem,) = store.tick()
    snoozed = store.snooze(rem.id, 10, client_id="desk")
    assert snoozed.status == "snoozed" and store.pending("desk") == []
    clock.advance(minutes=9)
    assert store.tick() == []
    clock.advance(minutes=2)
    (again,) = store.tick()
    assert again.id == rem.id and again.delivery_count == 2 and again.status == "delivered"
    acked = store.acknowledge(rem.id, client_id="desk")
    assert acked.status == "acknowledged" and store.pending("desk") == []
    with pytest.raises(Conflict):
        store.acknowledge(rem.id)
    assert store.get(rem.schedule_id).status == "done"  # a once rule finishes after firing
    with pytest.raises(ValidationFailed):
        store.snooze(rem.id, 0)


def test_pause_resume_cancel_and_reschedule(store, clock):
    sch = store.create(client_id="desk", kind="lesson", title="Lesson", rule=Rule(type="weekly", days=[4], time_local="19:30"))
    store.set_status(sch.id, "paused")
    clock.set(utc(2026, 10, 23, 19, 0))
    assert store.tick() == []  # paused schedules never fire
    resumed = store.set_status(sch.id, "active")
    assert parse_iso(resumed.next_run_at) == utc(2026, 10, 30, 19, 30)  # next Friday, now GMT
    moved = store.reschedule(sch.id, Rule(type="weekly", days=[1], time_local="07:15"))
    assert moved.rule.days == [1] and parse_iso(moved.next_run_at).astimezone(LONDON).strftime("%A %H:%M") == "Tuesday 07:15"
    store.set_status(sch.id, "cancelled")
    with pytest.raises(Conflict):
        store.set_status(sch.id, "active")
    with pytest.raises(ValidationFailed):
        store.create(client_id="desk", kind="reminder", title="past", rule=Rule(type="once", at_local="2020-01-01T10:00"))
