"""Application state: builds providers from configuration (or test overrides)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from companion_core.auth import Permission, TokenStore
from companion_core.clock import Clock, SystemClock
from companion_core.config import AppConfig
from companion_core.db import Database
from companion_core.logging import get_logger
from companion_integrations.factory import (
    build_cards,
    build_email,
    build_home,
    build_llm,
    build_stt,
    build_tts,
    build_vault,
    build_weather,
)
from companion_integrations.home.base import HomeProvider
from companion_integrations.llm.base import LLMProvider
from companion_integrations.speech.base import STTProvider, TTSProvider
from companion_vault.client import VaultClient
from companion_worker.queue import JobQueue
from companion_worker.recordings import RecordingStore
from companion_worker.scheduler import SchedulerStore

from .store import ConversationStore

log = get_logger(__name__)


@dataclass
class AppState:
    config: AppConfig
    tokens: TokenStore
    store: ConversationStore
    vault: VaultClient
    llm: LLMProvider
    home: HomeProvider | None
    clock: Clock
    stt: STTProvider | None = None
    tts: TTSProvider | None = None
    queue: Any = None
    recordings: Any = None
    scheduler: Any = None
    worker: Any = None
    weather: Any = None
    cards: Any = None
    email: Any = None
    warnings: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    perm: type[Permission] = Permission
    # filled by wire_up()
    home_access: Any = None
    gateway: Any = None
    router: Any = None
    orchestrator: Any = None
    extras: dict[str, Any] = field(default_factory=dict)

    def uptime_s(self) -> int:
        return int(time.time() - self.started_at)


def build_state(cfg: AppConfig, **overrides: Any) -> AppState:
    tokens, warnings = cfg.build_token_store()
    for w in warnings:
        log.warning(w)
    store = overrides.get("store") or ConversationStore(Database(cfg.brain_db_path))
    store.migrate()
    state = AppState(
        config=cfg,
        tokens=overrides.get("tokens") or tokens,
        store=store,
        vault=overrides.get("vault") or build_vault(cfg),
        llm=overrides.get("llm") or build_llm(cfg),
        home=overrides["home"] if "home" in overrides else build_home(cfg),
        clock=overrides.get("clock") or SystemClock(),
        stt=overrides["stt"] if "stt" in overrides else build_stt(cfg),
        tts=overrides["tts"] if "tts" in overrides else build_tts(cfg),
        warnings=warnings,
    )
    state.weather = overrides["weather"] if "weather" in overrides else build_weather(cfg, clock=state.clock)
    state.cards = overrides["cards"] if "cards" in overrides else build_cards(cfg, clock=state.clock)
    state.email = overrides["email"] if "email" in overrides else build_email(cfg)
    for name in ("weather", "cards", "email"):
        prov = getattr(state, name)
        if prov is not None:
            state.extras[name] = prov
    state.queue = JobQueue(store.db, state.clock)
    state.recordings = RecordingStore(store.db, cfg.media_dir, state.clock)
    state.scheduler = SchedulerStore(store.db, state.clock)
    if state.stt is not None:
        state.extras["stt"] = state.stt
    if state.tts is not None:
        state.extras["tts"] = state.tts
    wire_up(state)
    return state


def wire_up(state: AppState) -> None:
    from .orchestrator import Orchestrator
    from .router import DeterministicRouter
    from .tools.builtin import register_builtin
    from .tools.gateway import ToolGateway
    from .tools.home_access import HomeAccess

    state.home_access = HomeAccess(state.config, state.home)
    state.gateway = ToolGateway(state)
    register_builtin(state.gateway)
    state.router = DeterministicRouter(state.home_access, recordings=state.recordings)
    state.orchestrator = Orchestrator(state)
    state.worker = build_worker(state)


def build_worker(state: AppState) -> Any:
    """The job runner; started by the API lifespan only when worker.embedded is true."""
    from companion_worker.handlers import HANDLERS
    from companion_worker.runner import Worker
    from companion_worker.services import WorkerServices

    services = WorkerServices(config=state.config, vault=state.vault, stt=state.stt, llm=state.llm, recordings=state.recordings, queue=state.queue, clock=state.clock, scheduler=state.scheduler)
    cfg = state.config.worker
    return Worker(state.queue, HANDLERS, services, concurrency=cfg.concurrency, poll_interval_s=cfg.poll_interval_s, lease_s=cfg.lease_s, periodic=[state.scheduler.tick])
