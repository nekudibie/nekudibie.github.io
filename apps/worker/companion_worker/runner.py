"""Job runner: claims jobs, runs handlers with heartbeats, keeps interactive work flowing.

Two lanes: one slot is reserved for interactive jobs (priority < 20) so a long transcription
never blocks a short, user-facing job. Handlers receive a ``JobContext`` and must be
idempotent; they call ``ctx.progress()`` regularly, which also tells them to stop when the
job was cancelled.
"""

from __future__ import annotations

import asyncio
import socket
import traceback
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from companion_core.errors import Cancelled, CompanionError
from companion_core.ids import new_id
from companion_core.logging import get_logger

from .queue import Job, JobQueue

log = get_logger(__name__)


@dataclass
class JobContext:
    job: Job
    queue: JobQueue
    services: Any  # whatever the host provides (vault, stt, llm, config, store ...)
    lease_s: float = 60.0
    cancelled: bool = field(default=False)

    def progress(self, fraction: float | None = None, note: str | None = None) -> None:
        """Heartbeat + progress. Raises Cancelled when the user asked to stop."""
        if not self.queue.heartbeat(self.job.id, lease_s=self.lease_s, progress=fraction, note=note):
            self.cancelled = True
            raise Cancelled(f"job {self.job.id} cancelled")


Handler = Callable[[JobContext], Awaitable[dict[str, Any] | None]]


class Worker:
    def __init__(self, queue: JobQueue, handlers: Mapping[str, Handler], services: Any, *, concurrency: int = 2,
                 poll_interval_s: float = 1.0, lease_s: float = 60.0, worker_id: str | None = None,
                 periodic: list[Callable[[], Any]] | None = None) -> None:
        self.periodic = list(periodic or [])
        self.queue = queue
        self.handlers = handlers
        self.services = services
        self.concurrency = max(1, concurrency)
        self.poll_interval_s = poll_interval_s
        self.lease_s = lease_s
        self.worker_id = worker_id or f"{socket.gethostname()}-{new_id('wrk')[-6:]}"
        self._stop = asyncio.Event()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.processed = 0

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        log.info("worker started", extra={"worker_id": self.worker_id, "handlers": sorted(self.handlers), "concurrency": self.concurrency})
        try:
            while not self._stop.is_set():
                claimed = await self.tick()
                if not claimed:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_s)
                    except TimeoutError:
                        pass
        finally:
            if self._tasks:
                await asyncio.gather(*self._tasks.values(), return_exceptions=True)
            log.info("worker stopped", extra={"worker_id": self.worker_id, "processed": self.processed})

    async def tick(self) -> int:
        """Run periodic hooks (e.g. the scheduler), reclaim expired leases, claim free slots. Returns jobs claimed."""
        for hook in self.periodic:
            try:
                await asyncio.to_thread(hook)
            except Exception:  # noqa: BLE001
                log.exception("periodic hook failed", extra={"hook": getattr(hook, "__name__", str(hook))})
        self.queue.reclaim_expired()
        self._tasks = {k: t for k, t in self._tasks.items() if not t.done()}
        free = self.concurrency - len(self._tasks)
        claimed = 0
        kinds = list(self.handlers)
        while free > 0:
            running_background = sum(1 for t in self._tasks.values() if t.get_name().startswith("bg:"))
            # keep one slot for interactive work: background may only take concurrency-1 slots
            job = self.queue.claim(self.worker_id, kinds=kinds, lease_s=self.lease_s, max_priority=19)
            if job is None and running_background < max(1, self.concurrency - 1):
                job = self.queue.claim(self.worker_id, kinds=kinds, lease_s=self.lease_s, min_priority=20)
            if job is None:
                break
            lane = "ia" if job.priority < 20 else "bg"
            task = asyncio.create_task(self._run(job), name=f"{lane}:{job.id}")
            self._tasks[job.id] = task
            claimed += 1
            free -= 1
        return claimed

    async def run_until_idle(self, *, max_seconds: float = 30.0) -> int:
        """Test/CLI helper: process everything currently runnable, then return the count."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_seconds
        total = 0
        while loop.time() < deadline:
            n = await self.tick()
            total += n
            if n == 0 and not self._tasks:
                break
            if self._tasks:
                await asyncio.wait(list(self._tasks.values()), timeout=0.2)
                self._tasks = {k: t for k, t in self._tasks.items() if not t.done()}
        return total

    async def _run(self, job: Job) -> None:
        handler = self.handlers.get(job.kind)
        ctx = JobContext(job=job, queue=self.queue, services=self.services, lease_s=self.lease_s)
        if handler is None:
            self.queue.fail(job.id, f"no handler for {job.kind}", retry=False)
            return
        try:
            result = await handler(ctx)
            self.queue.succeed(job.id, result or {})
            log.info("job done", extra={"job": job.id, "kind": job.kind})
        except Cancelled:
            self.queue.mark_cancelled(job.id)
            log.info("job cancelled", extra={"job": job.id, "kind": job.kind})
        except CompanionError as exc:
            self.queue.fail(job.id, f"{exc.code}: {exc.message}", retry=exc.code in {"upstream_unavailable", "upstream_error", "timeout"})
            log.warning("job failed", extra={"job": job.id, "kind": job.kind, "code": exc.code})
        except Exception as exc:  # noqa: BLE001
            self.queue.fail(job.id, f"{exc.__class__.__name__}: {exc}", retry=True)
            log.error("job crashed", extra={"job": job.id, "kind": job.kind, "trace": traceback.format_exc()[-800:]})
        finally:
            self.processed += 1
