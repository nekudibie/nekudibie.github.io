"""Persistent job queue on brain.db.

Guarantees: a job is claimed by exactly one worker (atomic UPDATE with a lease); a crashed
worker's lease expires and the job is re-queued with its attempt count intact; handlers are
expected to be idempotent (resume from their own checkpoints); interactive work (priority
< 20) is claimed before background work regardless of age.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from companion_core.clock import Clock, SystemClock, iso, parse_iso
from companion_core.db import Database
from companion_core.errors import Conflict, NotFound
from companion_core.ids import new_id
from pydantic import BaseModel, ConfigDict, Field

INTERACTIVE = 10
BACKGROUND = 50
BULK = 90


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: str
    payload: dict[str, Any]
    idempotency_key: str | None
    priority: int
    status: str
    attempts: int
    max_attempts: int
    run_after: str
    leased_until: str | None
    worker_id: str | None
    progress: float
    progress_note: str | None
    result: dict[str, Any] | None
    error: str | None
    cancel_requested: bool
    client_id: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class JobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: str
    kind: str
    note: str | None = None


class JobQueue:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or SystemClock()

    def _now(self) -> str:
        return iso(self.clock.now())

    @staticmethod
    def _row(r: Any) -> Job:
        return Job(
            id=r["id"], kind=r["kind"], payload=json.loads(r["payload_json"]), idempotency_key=r["idempotency_key"], priority=r["priority"],
            status=r["status"], attempts=r["attempts"], max_attempts=r["max_attempts"], run_after=r["run_after"], leased_until=r["leased_until"],
            worker_id=r["worker_id"], progress=r["progress"], progress_note=r["progress_note"],
            result=json.loads(r["result_json"]) if r["result_json"] else None, error=r["error"], cancel_requested=bool(r["cancel_requested"]),
            client_id=r["client_id"], created_at=r["created_at"], updated_at=r["updated_at"], started_at=r["started_at"], finished_at=r["finished_at"],
        )

    def _event(self, conn: Any, job_id: str, kind: str, note: str | None = None) -> None:
        conn.execute("INSERT INTO job_events(job_id, at, kind, note) VALUES (?,?,?,?)", (job_id, self._now(), kind, note))

    # -- producer --------------------------------------------------------
    def enqueue(self, kind: str, payload: dict[str, Any], *, idempotency_key: str | None = None, priority: int = BACKGROUND,
                run_after: str | None = None, max_attempts: int = 3, client_id: str | None = None) -> Job:
        now = self._now()
        with self.db.transaction() as conn:
            if idempotency_key:
                row = conn.execute("SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                if row:
                    return self._row(row)
            jid = new_id("job")
            conn.execute(
                "INSERT INTO jobs(id, kind, payload_json, idempotency_key, priority, status, max_attempts, run_after, client_id, created_at, updated_at)"
                " VALUES (?,?,?,?,?,'queued',?,?,?,?,?)",
                (jid, kind, json.dumps(payload, default=str), idempotency_key, priority, max_attempts, run_after or now, client_id, now, now),
            )
            self._event(conn, jid, "enqueued", kind)
        return self.get(jid)

    # -- worker ----------------------------------------------------------
    def reclaim_expired(self) -> int:
        """Return crashed workers' jobs to the queue (lease expired while 'running')."""
        now = self._now()
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT id FROM jobs WHERE status = 'running' AND leased_until IS NOT NULL AND leased_until < ?", (now,)).fetchall()
            for r in rows:
                conn.execute("UPDATE jobs SET status = 'queued', leased_until = NULL, worker_id = NULL, updated_at = ? WHERE id = ?", (now, r["id"]))
                self._event(conn, r["id"], "reclaimed", "lease expired")
        return len(rows)

    def claim(self, worker_id: str, *, kinds: list[str] | None = None, lease_s: float = 60.0, max_priority: int | None = None, min_priority: int | None = None) -> Job | None:
        now = self._now()
        lease_until = iso(self.clock.now() + timedelta(seconds=lease_s))
        sql = "SELECT id FROM jobs WHERE status = 'queued' AND run_after <= ? AND cancel_requested = 0"
        params: list[Any] = [now]
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += kinds
        if max_priority is not None:
            sql += " AND priority <= ?"
            params.append(max_priority)
        if min_priority is not None:
            sql += " AND priority >= ?"
            params.append(min_priority)
        sql += " ORDER BY priority ASC, run_after ASC, created_at ASC LIMIT 1"
        with self.db.transaction() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            if not row:
                return None
            cur = conn.execute(
                "UPDATE jobs SET status = 'running', worker_id = ?, leased_until = ?, heartbeat_at = ?, attempts = attempts + 1,"
                " started_at = COALESCE(started_at, ?), updated_at = ? WHERE id = ? AND status = 'queued'",
                (worker_id, lease_until, now, now, now, row["id"]),
            )
            if cur.rowcount != 1:
                return None
            self._event(conn, row["id"], "claimed", worker_id)
        return self.get(row["id"])

    def heartbeat(self, job_id: str, *, lease_s: float = 60.0, progress: float | None = None, note: str | None = None) -> bool:
        """Extend the lease; returns False when cancellation was requested."""
        now = self._now()
        lease_until = iso(self.clock.now() + timedelta(seconds=lease_s))
        with self.db.transaction() as conn:
            sets = "leased_until = ?, heartbeat_at = ?, updated_at = ?"
            params: list[Any] = [lease_until, now, now]
            if progress is not None:
                sets += ", progress = ?"
                params.append(max(0.0, min(1.0, progress)))
            if note is not None:
                sets += ", progress_note = ?"
                params.append(note[:300])
            params.append(job_id)
            conn.execute(f"UPDATE jobs SET {sets} WHERE id = ?", tuple(params))  # noqa: S608 - fixed column names
            if progress is not None or note:
                self._event(conn, job_id, "progress", f"{progress if progress is not None else ''} {note or ''}".strip())
            row = conn.execute("SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return not (row and row["cancel_requested"])

    def succeed(self, job_id: str, result: dict[str, Any] | None = None) -> Job:
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'succeeded', progress = 1, result_json = ?, leased_until = NULL, finished_at = ?, updated_at = ? WHERE id = ?",
                (json.dumps(result or {}, default=str), now, now, job_id),
            )
            self._event(conn, job_id, "succeeded")
        return self.get(job_id)

    def fail(self, job_id: str, error: str, *, retry: bool = True, backoff_s: float = 30.0) -> Job:
        now = self._now()
        job = self.get(job_id)
        with self.db.transaction() as conn:
            if retry and job.attempts < job.max_attempts and not job.cancel_requested:
                delay = backoff_s * (2 ** (job.attempts - 1))
                run_after = iso(self.clock.now() + timedelta(seconds=delay))
                conn.execute(
                    "UPDATE jobs SET status = 'queued', error = ?, leased_until = NULL, worker_id = NULL, run_after = ?, updated_at = ? WHERE id = ?",
                    (error[:1000], run_after, now, job_id),
                )
                self._event(conn, job_id, "retry", f"attempt {job.attempts} failed: {error[:200]}; next at {run_after}")
            else:
                conn.execute(
                    "UPDATE jobs SET status = 'failed', error = ?, leased_until = NULL, finished_at = ?, updated_at = ? WHERE id = ?",
                    (error[:1000], now, now, job_id),
                )
                self._event(conn, job_id, "failed", error[:200])
        return self.get(job_id)

    def cancel(self, job_id: str) -> Job:
        now = self._now()
        job = self.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            raise Conflict(f"job is already {job.status}")
        with self.db.transaction() as conn:
            if job.status == "queued":
                conn.execute("UPDATE jobs SET status = 'cancelled', cancel_requested = 1, finished_at = ?, updated_at = ? WHERE id = ?", (now, now, job_id))
            else:  # running: the handler sees the flag at its next heartbeat and stops
                conn.execute("UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?", (now, job_id))
            self._event(conn, job_id, "cancelled", "requested")
        return self.get(job_id)

    def mark_cancelled(self, job_id: str) -> Job:
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute("UPDATE jobs SET status = 'cancelled', leased_until = NULL, finished_at = ?, updated_at = ? WHERE id = ?", (now, now, job_id))
            self._event(conn, job_id, "cancelled", "stopped by handler")
        return self.get(job_id)

    def retry(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status not in {"failed", "cancelled"}:
            raise Conflict(f"job is {job.status}; only failed or cancelled jobs can be retried")
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'queued', cancel_requested = 0, error = NULL, run_after = ?, finished_at = NULL, leased_until = NULL,"
                " worker_id = NULL, max_attempts = attempts + 3, updated_at = ? WHERE id = ?",
                (now, now, job_id),
            )
            self._event(conn, job_id, "enqueued", "manual retry")
        return self.get(job_id)

    # -- reads -----------------------------------------------------------
    def get(self, job_id: str) -> Job:
        row = self.db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not row:
            raise NotFound(f"job {job_id} not found")
        return self._row(row)

    def list(self, *, client_id: str | None = None, status: list[str] | None = None, kind: str | None = None, limit: int = 50) -> list[Job]:
        sql = "SELECT * FROM jobs WHERE 1=1"
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
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._row(r) for r in self.db.query(sql, tuple(params))]

    def events(self, job_id: str, limit: int = 100) -> list[JobEvent]:
        rows = self.db.query("SELECT at, kind, note FROM job_events WHERE job_id = ? ORDER BY id DESC LIMIT ?", (job_id, limit))
        return [JobEvent(at=r["at"], kind=r["kind"], note=r["note"]) for r in reversed(rows)]

    def counts(self) -> dict[str, int]:
        return {r["status"]: r["n"] for r in self.db.query("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")}

    def due_in_s(self, job: Job) -> float:
        return (parse_iso(job.run_after) - self.clock.now()).total_seconds()


__all__ = ["JobQueue", "Job", "JobEvent", "INTERACTIVE", "BACKGROUND", "BULK", "Field"]
