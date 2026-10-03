from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from companion_api.store import ConversationStore
from companion_core.clock import FakeClock, parse_iso
from companion_core.db import Database
from companion_core.errors import Conflict
from companion_worker.queue import BACKGROUND, BULK, INTERACTIVE, JobQueue
from companion_worker.runner import JobContext, Worker


@pytest.fixture
def clock():
    return FakeClock(datetime(2026, 10, 3, 9, 0, tzinfo=UTC))


@pytest.fixture
def q(tmp_path, clock):
    db = Database(tmp_path / "brain.db")
    ConversationStore(db).migrate()
    return JobQueue(db, clock)


def test_enqueue_is_idempotent_by_key(q):
    a = q.enqueue("transcribe_recording", {"recording_id": "r1"}, idempotency_key="transcribe:r1")
    b = q.enqueue("transcribe_recording", {"recording_id": "r1"}, idempotency_key="transcribe:r1")
    assert a.id == b.id and q.counts() == {"queued": 1}
    assert [e.kind for e in q.events(a.id)] == ["enqueued"]


def test_interactive_claimed_before_older_bulk(q):
    q.enqueue("bulk", {}, priority=BULK)
    q.enqueue("bg", {}, priority=BACKGROUND)
    ia = q.enqueue("ia", {}, priority=INTERACTIVE)
    assert q.claim("w1").id == ia.id
    assert q.claim("w1").kind == "bg"
    assert q.claim("w1").kind == "bulk"
    assert q.claim("w1") is None


def test_lease_expiry_requeues_after_crash(q, clock):
    j = q.enqueue("x", {})
    claimed = q.claim("w1", lease_s=60)
    assert claimed.status == "running" and claimed.attempts == 1
    assert q.reclaim_expired() == 0
    clock.advance(seconds=61)
    assert q.reclaim_expired() == 1
    again = q.claim("w2", lease_s=60)
    assert again.id == j.id and again.attempts == 2 and again.worker_id == "w2"
    assert "reclaimed" in [e.kind for e in q.events(j.id)]


def test_heartbeat_reports_cancellation(q):
    j = q.enqueue("x", {})
    q.claim("w1")
    assert q.heartbeat(j.id, progress=0.3, note="working") is True
    q.cancel(j.id)
    assert q.heartbeat(j.id, progress=0.5) is False
    assert q.get(j.id).progress == 0.5 and q.get(j.id).cancel_requested
    with pytest.raises(Conflict):
        q.cancel(q.mark_cancelled(j.id).id)


def test_fail_retries_with_backoff_then_gives_up(q, clock):
    j = q.enqueue("x", {}, max_attempts=2)
    q.claim("w1")
    f = q.fail(j.id, "boom", retry=True, backoff_s=30)
    assert f.status == "queued" and (parse_iso(f.run_after) - clock.now()).total_seconds() == pytest.approx(30, abs=1)
    assert q.claim("w1") is None  # not due yet
    clock.advance(seconds=31)
    assert q.claim("w1").attempts == 2
    f = q.fail(j.id, "boom again", retry=True)
    assert f.status == "failed" and f.error == "boom again"
    r = q.retry(j.id)
    assert r.status == "queued" and r.max_attempts == 5


def test_cancel_queued_job_never_runs(q):
    j = q.enqueue("x", {})
    q.cancel(j.id)
    assert q.get(j.id).status == "cancelled" and q.claim("w1") is None


@pytest.mark.asyncio
async def test_runner_executes_handlers_and_records_outcomes(q):
    seen = []

    async def ok(ctx: JobContext):
        ctx.progress(0.5, "half")
        seen.append(ctx.job.payload["n"])
        return {"n": ctx.job.payload["n"]}

    async def crash(ctx: JobContext):
        raise RuntimeError("kaboom")

    a = q.enqueue("ok", {"n": 1})
    b = q.enqueue("crash", {}, max_attempts=1)
    c = q.enqueue("unknown_kind", {})
    w = Worker(q, {"ok": ok, "crash": crash, "unknown_kind": None}, services=None, concurrency=2)  # type: ignore[dict-item]
    await w.run_until_idle(max_seconds=5)
    assert seen == [1] and q.get(a.id).status == "succeeded" and q.get(a.id).result == {"n": 1}
    assert q.get(b.id).status == "failed" and "kaboom" in (q.get(b.id).error or "")
    assert q.get(c.id).status == "failed"


@pytest.mark.asyncio
async def test_runner_reserves_a_slot_for_interactive_work(q):
    release = asyncio.Event()
    order = []

    async def slow_bg(ctx: JobContext):
        order.append(("start", ctx.job.kind))
        await release.wait()
        return {}

    async def quick_ia(ctx: JobContext):
        order.append(("start", ctx.job.kind))
        return {}

    for _ in range(3):
        q.enqueue("slow_bg", {}, priority=BACKGROUND)
    w = Worker(q, {"slow_bg": slow_bg, "quick_ia": quick_ia}, services=None, concurrency=2)
    assert await w.tick() == 1  # only one background slot is used; the other is kept free
    q.enqueue("quick_ia", {}, priority=INTERACTIVE)
    assert await w.tick() == 1  # the interactive job gets the reserved slot immediately
    await asyncio.sleep(0.05)
    assert ("start", "quick_ia") in order
    release.set()
    await w.run_until_idle(max_seconds=5)
    assert q.counts().get("succeeded") == 4


@pytest.mark.asyncio
async def test_cancelled_running_job_stops_at_next_progress(q):
    async def loops(ctx: JobContext):
        for i in range(50):
            ctx.progress(i / 50)
            await asyncio.sleep(0.01)
        return {}

    j = q.enqueue("loops", {})
    w = Worker(q, {"loops": loops}, services=None, concurrency=1)
    await w.tick()
    await asyncio.sleep(0.05)
    q.cancel(j.id)
    await w.run_until_idle(max_seconds=5)
    assert q.get(j.id).status == "cancelled"
