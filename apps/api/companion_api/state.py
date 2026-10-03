"""Application state: builds providers from configuration (or test overrides)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from companion_core.auth import Permission, TokenStore
from companion_core.clock import Clock, SystemClock
from companion_core.config import AppConfig
from companion_core.db import Database
from companion_core.errors import ConfigError
from companion_core.logging import get_logger
from companion_integrations.home.base import HomeProvider
from companion_integrations.home.fixture import FixtureHomeProvider
from companion_integrations.llm.base import LLMProvider
from companion_integrations.llm.fixture import FixtureProvider
from companion_integrations.llm.ollama import OllamaProvider
from companion_vault.client import HttpVaultClient, LocalVaultClient, VaultClient
from companion_vault.service import VaultService

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


def build_llm(cfg: AppConfig) -> LLMProvider:
    if cfg.llm.provider == "ollama":
        return OllamaProvider(
            cfg.llm.base_url, cfg.llm.model, timeout_s=cfg.llm.timeout_s, connect_timeout_s=cfg.llm.connect_timeout_s,
            keep_alive=cfg.llm.keep_alive, num_ctx=cfg.llm.num_ctx, temperature=cfg.llm.temperature, think=cfg.llm.think,
        )
    return FixtureProvider()


def build_home(cfg: AppConfig) -> HomeProvider | None:
    if cfg.home.provider == "disabled":
        return None
    if cfg.home.provider == "home_assistant":
        from companion_integrations.home.home_assistant import HomeAssistantProvider

        token = cfg.secret(cfg.home.token_env)
        if not token:
            raise ConfigError(f"home.provider is home_assistant but {cfg.home.token_env} is not set")
        return HomeAssistantProvider(cfg.home.base_url, token, timeout_s=cfg.home.timeout_s)
    return FixtureHomeProvider()


def build_vault(cfg: AppConfig) -> VaultClient:
    if cfg.vault.mode == "remote":
        token = cfg.vault_service_token()
        if not token:
            raise ConfigError(f"vault.mode is remote but {cfg.vault.token_env} is not set")
        return HttpVaultClient(cfg.vault.url, token, timeout_s=cfg.vault.timeout_s)
    svc = VaultService(Database(cfg.vault_db_path), chunk_chars=cfg.vault.chunk_chars, chunk_overlap_chars=cfg.vault.chunk_overlap_chars)
    svc.migrate()
    return LocalVaultClient(svc)


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
        warnings=warnings,
    )
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
    state.router = DeterministicRouter(state.home_access)
    state.orchestrator = Orchestrator(state)
