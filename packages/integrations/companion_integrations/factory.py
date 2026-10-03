"""Build providers from configuration. Shared by the API and the worker so both roles
construct identical adapters without one importing the other."""

from __future__ import annotations

from companion_core.config import AppConfig
from companion_core.db import Database
from companion_core.errors import ConfigError

from .home.base import HomeProvider
from .home.fixture import FixtureHomeProvider
from .llm.base import LLMProvider
from .llm.fixture import FixtureProvider
from .llm.ollama import OllamaProvider
from .speech.base import STTProvider, TTSProvider
from .speech.fixture import FixtureSTT, FixtureTTS


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
        from .home.home_assistant import HomeAssistantProvider

        token = cfg.secret(cfg.home.token_env)
        if not token:
            raise ConfigError(f"home.provider is home_assistant but {cfg.home.token_env} is not set")
        return HomeAssistantProvider(cfg.home.base_url, token, timeout_s=cfg.home.timeout_s)
    return FixtureHomeProvider()


def build_stt(cfg: AppConfig) -> STTProvider | None:
    if cfg.stt.provider == "disabled":
        return None
    if cfg.stt.provider == "faster_whisper":
        from .speech.faster_whisper_stt import FasterWhisperSTT

        return FasterWhisperSTT(
            cfg.stt.model, device=cfg.stt.device, compute_type=cfg.stt.compute_type, cpu_threads=cfg.stt.cpu_threads,
            download_root=cfg.data_dir / "models" / "whisper", language=cfg.stt.language, max_audio_s=cfg.stt.max_audio_s,
        )
    return FixtureSTT()


def build_tts(cfg: AppConfig) -> TTSProvider | None:
    if cfg.tts.provider == "disabled":
        return None
    if cfg.tts.provider == "piper":
        from .speech.piper_tts import PiperTTS

        return PiperTTS(cfg.tts.voice, cfg.tts_voices_dir, length_scale=cfg.tts.length_scale)
    return FixtureTTS()


def build_vault(cfg: AppConfig):  # type: ignore[no-untyped-def]  # -> VaultClient (import kept local to avoid a hard dependency cycle in type checking)
    from companion_vault.client import HttpVaultClient, LocalVaultClient
    from companion_vault.service import VaultService

    if cfg.vault.mode == "remote":
        token = cfg.vault_service_token()
        if not token:
            raise ConfigError(f"vault.mode is remote but {cfg.vault.token_env} is not set")
        return HttpVaultClient(cfg.vault.url, token, timeout_s=cfg.vault.timeout_s)
    svc = VaultService(Database(cfg.vault_db_path), chunk_chars=cfg.vault.chunk_chars, chunk_overlap_chars=cfg.vault.chunk_overlap_chars)
    svc.migrate()
    return LocalVaultClient(svc)


def build_weather(cfg: AppConfig, *, clock=None):  # type: ignore[no-untyped-def]
    if cfg.weather.provider == "disabled":
        return None
    if cfg.weather.provider == "open_meteo":
        from .weather.open_meteo import build_open_meteo

        return build_open_meteo(cfg, clock=clock)
    from .weather.fixture import FixtureWeatherProvider

    return FixtureWeatherProvider(clock=clock)


def build_cards(cfg: AppConfig, *, clock=None):  # type: ignore[no-untyped-def]
    if cfg.mtg.provider == "disabled":
        return None
    if cfg.mtg.provider == "scryfall":
        from .mtg.scryfall import ScryfallProvider

        return ScryfallProvider(cfg.mtg_cache_dir, user_agent=cfg.mtg.user_agent, cache_ttl_s=cfg.mtg.cache_ttl_s, timeout_s=cfg.mtg.timeout_s, clock=clock)
    from .mtg.fixture import FixtureCardProvider

    return FixtureCardProvider()


def build_email(cfg: AppConfig):  # type: ignore[no-untyped-def]
    if cfg.email.provider == "disabled":
        return None
    if cfg.email.provider == "gmail":
        from .email.gmail import GmailOAuth, GmailProvider
        from .email.tokens import TokenVault

        client_id = cfg.secret(cfg.email.client_id_env)
        client_secret = cfg.secret(cfg.email.client_secret_env)
        key = cfg.secret(cfg.email.token_key_env)
        if not (client_id and client_secret and key):
            raise ConfigError(f"email.provider is gmail: set {cfg.email.client_id_env}, {cfg.email.client_secret_env} and {cfg.email.token_key_env}")
        return GmailProvider(GmailOAuth(client_id, client_secret), TokenVault(cfg.email_token_path, key), account_label=cfg.email.account_label)
    from .email.fixture import FixtureEmailProvider

    return FixtureEmailProvider()
