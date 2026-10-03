"""What handlers can reach. Built from AppState (embedded) or from config (standalone)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from companion_core.clock import Clock, SystemClock
from companion_core.config import AppConfig
from companion_core.db import Database

from .queue import JobQueue
from .recordings import RecordingStore
from .scheduler import SchedulerStore


@dataclass
class WorkerServices:
    config: AppConfig
    vault: Any
    stt: Any
    llm: Any
    recordings: RecordingStore
    queue: JobQueue
    clock: Clock
    scheduler: SchedulerStore | None = None


def build_services(cfg: AppConfig, *, db: Database | None = None) -> WorkerServices:
    from companion_integrations.factory import build_llm, build_stt, build_vault

    clock = SystemClock()
    db = db or Database(cfg.brain_db_path)
    return WorkerServices(
        config=cfg, vault=build_vault(cfg), stt=build_stt(cfg), llm=build_llm(cfg),
        recordings=RecordingStore(db, cfg.media_dir, clock), queue=JobQueue(db, clock), clock=clock, scheduler=SchedulerStore(db, clock),
    )
