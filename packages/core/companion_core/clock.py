"""Clock abstraction so schedules and timeouts can be tested deterministically."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class FakeClock:
    """A controllable clock for tests. Always timezone-aware (UTC)."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(**kwargs)

    def set(self, when: datetime) -> None:
        self._now = when.astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: datetime) -> str:
    """Canonical storage format: ISO 8601 in UTC with millisecond precision and a Z suffix."""
    if dt.tzinfo is None:
        raise ValueError("refusing to serialise a naive datetime")
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
