"""Typed configuration for every role.

One YAML file describes an *instance*; which services actually run on a host is
decided by the process you start (``companion-api``, ``companion-vault``,
``companion-worker``, ``companion-audio``) and by the ``mode`` fields below
(``vault.mode: embedded|remote``, ``worker.embedded``). Moving a service to
another host is a configuration change, never an application-logic change.

Secrets are never written in YAML. Fields ending in ``_env`` name an environment
variable; ``.env`` in the repository root is loaded first (process environment wins).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .auth import ROLE_PERMISSIONS, ClientIdentity, Permission, TokenStore, hash_token
from .envfile import load_env_file
from .errors import ConfigError
from .logging import get_logger, register_secret
from .version import repo_root

log = get_logger(__name__)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InstanceConfig(_Strict):
    name: str = "companion-dev"
    timezone: str = "Europe/London"
    data_dir: Path = Path("./data")
    environment: Literal["development", "production"] = "development"
    owner_name: str = "Neku"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone {v!r}") from exc
        return v


class LoggingConfig(_Strict):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "text"] = "json"


class ApiConfig(_Strict):
    host: str = "127.0.0.1"
    port: int = 8710
    public_base_url: str | None = None
    cors_origins: list[str] = Field(default_factory=list)
    serve_desk_ui: bool = True
    desk_dist_dir: Path | None = None
    request_timeout_s: float = 120.0


class VaultConfig(_Strict):
    mode: Literal["embedded", "remote"] = "embedded"
    host: str = "127.0.0.1"
    port: int = 8720
    url: str = "http://127.0.0.1:8720"
    token_env: str = "COMPANION_VAULT_TOKEN"  # noqa: S105 - env var name, not a secret
    db_path: Path | None = None
    files_dir: Path | None = None
    backup_dir: Path | None = None
    chunk_chars: int = 1200
    chunk_overlap_chars: int = 150
    timeout_s: float = 10.0


class BrainConfig(_Strict):
    db_path: Path | None = None
    media_dir: Path | None = None


class WorkerConfig(_Strict):
    embedded: bool = True
    poll_interval_s: float = 1.0
    concurrency: int = 2
    heartbeat_s: float = 10.0
    lease_s: float = 60.0


class LlmConfig(_Strict):
    provider: Literal["fixture", "ollama"] = "fixture"
    base_url: str = "http://127.0.0.1:11434"
    model: str = ""
    timeout_s: float = 90.0
    connect_timeout_s: float = 3.0
    keep_alive: str = "10m"
    num_ctx: int = 8192
    temperature: float = 0.3
    max_tool_rounds: int = 4
    think: bool | None = None

    @model_validator(mode="after")
    def _needs_model(self) -> LlmConfig:
        if self.provider == "ollama" and not self.model:
            raise ValueError("llm.model is required when llm.provider is 'ollama' (run `ollama list` on the brain host)")
        return self


class HomeConfig(_Strict):
    provider: Literal["disabled", "fixture", "home_assistant"] = "fixture"
    base_url: str = "http://homeassistant.local:8123"
    token_env: str = "COMPANION_HA_TOKEN"  # noqa: S105 - env var name, not a secret
    timeout_s: float = 10.0
    allowed_entities: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(
        default_factory=lambda: ["light", "switch", "scene", "camera", "sensor", "binary_sensor", "input_boolean"]
    )
    scenes: dict[str, str] = Field(default_factory=dict)  # friendly name -> scene entity_id
    aliases: dict[str, str] = Field(default_factory=dict)  # spoken name -> entity_id
    cameras: dict[str, str] = Field(default_factory=dict)  # friendly name -> camera entity_id


class SttConfig(_Strict):
    provider: Literal["disabled", "fixture", "faster_whisper"] = "fixture"
    model: str = "base"
    device: Literal["cpu", "cuda", "auto"] = "cpu"
    compute_type: str = "int8"
    language: str | None = "en"
    cpu_threads: int = 0
    max_audio_s: float = 120.0


class TtsConfig(_Strict):
    provider: Literal["disabled", "fixture", "piper"] = "fixture"
    voice: str = "en_GB-alan-medium"
    voices_dir: Path | None = None
    length_scale: float = 1.0


class WakeWordConfig(_Strict):
    enabled: bool = False
    provider: Literal["disabled", "openwakeword"] = "disabled"
    model: str = "hey_jarvis"
    threshold: float = 0.6


class WeatherConfig(_Strict):
    provider: Literal["disabled", "fixture", "open_meteo"] = "fixture"
    latitude: float | None = None
    longitude: float | None = None
    location_name: str = ""
    cache_ttl_s: int = 1800
    timeout_s: float = 10.0


class EmailConfig(_Strict):
    provider: Literal["disabled", "fixture", "gmail"] = "fixture"
    account_label: str = "personal"
    client_id_env: str = "COMPANION_GMAIL_CLIENT_ID"
    client_secret_env: str = "COMPANION_GMAIL_CLIENT_SECRET"  # noqa: S105 - env var name, not a secret
    token_key_env: str = "COMPANION_TOKEN_KEY"  # noqa: S105 - env var name, not a secret
    token_path: Path | None = None
    max_results: int = 25
    allow_bulk_ingest: bool = False  # when true the embedded worker syncs orders in the background
    orders_sync_interval_min: int = Field(default=60, ge=5, le=1440)
    orders_sync_days: int = Field(default=30, ge=1, le=365)


class MtgConfig(_Strict):
    provider: Literal["disabled", "fixture", "scryfall"] = "fixture"
    cache_dir: Path | None = None
    cache_ttl_s: int = 86400
    user_agent: str = "NekuDeskCompanion/0.1 (personal, local-first)"
    timeout_s: float = 10.0


class TutorConfig(_Strict):
    enabled: bool = True
    reminder_lead_minutes: int = 0
    missed_grace_minutes: int = 120


class RoboticsConfig(_Strict):
    mode: Literal["disabled", "simulated"] = "simulated"
    watchdog_timeout_s: float = 0.5
    max_linear_speed_mps: float = 0.3
    max_angular_speed_rps: float = 0.8
    max_command_duration_s: float = 5.0


class ClientConfig(_Strict):
    id: str
    role: str
    label: str = ""
    token_env: str | None = None
    token_sha256: str | None = None
    home_entities: list[str] | None = None
    memory_scopes: list[str] = Field(default_factory=lambda: ["owner", "shared"])

    @model_validator(mode="after")
    def _one_source(self) -> ClientConfig:
        if self.role not in ROLE_PERMISSIONS:
            raise ValueError(f"client {self.id!r}: unknown role {self.role!r}; known: {sorted(ROLE_PERMISSIONS)}")
        if bool(self.token_env) == bool(self.token_sha256):
            raise ValueError(f"client {self.id!r}: set exactly one of token_env or token_sha256")
        if not self.id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"client id {self.id!r} must be alphanumeric with - or _")
        return self


class AppConfig(_Strict):
    instance: InstanceConfig = Field(default_factory=InstanceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    home: HomeConfig = Field(default_factory=HomeConfig)
    stt: SttConfig = Field(default_factory=SttConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    wake_word: WakeWordConfig = Field(default_factory=WakeWordConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    mtg: MtgConfig = Field(default_factory=MtgConfig)
    tutor: TutorConfig = Field(default_factory=TutorConfig)
    robotics: RoboticsConfig = Field(default_factory=RoboticsConfig)
    clients: list[ClientConfig] = Field(default_factory=list)

    # Set by the loader; not part of the YAML.
    source_path: Path | None = Field(default=None, exclude=True)
    base_dir: Path = Field(default_factory=repo_root, exclude=True)

    # -- resolved paths --------------------------------------------------
    def _abs(self, p: Path) -> Path:
        return p if p.is_absolute() else (self.base_dir / p).resolve()

    @property
    def data_dir(self) -> Path:
        return self._abs(self.instance.data_dir)

    @property
    def vault_db_path(self) -> Path:
        return self._abs(self.vault.db_path) if self.vault.db_path else self.data_dir / "vault" / "vault.db"

    @property
    def vault_files_dir(self) -> Path:
        return self._abs(self.vault.files_dir) if self.vault.files_dir else self.data_dir / "vault" / "files"

    @property
    def vault_backup_dir(self) -> Path:
        return self._abs(self.vault.backup_dir) if self.vault.backup_dir else self.data_dir / "backups"

    @property
    def brain_db_path(self) -> Path:
        return self._abs(self.brain.db_path) if self.brain.db_path else self.data_dir / "brain" / "brain.db"

    @property
    def media_dir(self) -> Path:
        return self._abs(self.brain.media_dir) if self.brain.media_dir else self.data_dir / "brain" / "media"

    @property
    def desk_dist_dir(self) -> Path:
        return self._abs(self.api.desk_dist_dir) if self.api.desk_dist_dir else self.base_dir / "apps" / "desk" / "dist"

    @property
    def mtg_cache_dir(self) -> Path:
        return self._abs(self.mtg.cache_dir) if self.mtg.cache_dir else self.data_dir / "cache" / "scryfall"

    @property
    def tts_voices_dir(self) -> Path:
        return self._abs(self.tts.voices_dir) if self.tts.voices_dir else self.data_dir / "voices"

    @property
    def email_token_path(self) -> Path:
        return self._abs(self.email.token_path) if self.email.token_path else self.data_dir / "secrets" / "email_tokens.enc"

    # -- secrets ---------------------------------------------------------
    def secret(self, env_name: str, *, required: bool = False) -> str | None:
        value = os.environ.get(env_name) or None
        if value:
            register_secret(value)
        elif required:
            raise ConfigError(f"environment variable {env_name} is required but not set")
        return value

    def vault_service_token(self) -> str | None:
        return self.secret(self.vault.token_env)

    def build_token_store(self) -> tuple[TokenStore, list[str]]:
        """Resolve configured clients to a token store. Returns (store, warnings)."""
        store = TokenStore()
        warnings: list[str] = []
        for c in self.clients:
            if c.token_env:
                raw = self.secret(c.token_env)
                if not raw:
                    warnings.append(f"client {c.id!r} disabled: environment variable {c.token_env} not set")
                    continue
                if len(raw) < 16:
                    warnings.append(f"client {c.id!r} disabled: token in {c.token_env} is shorter than 16 characters")
                    continue
                digest = hash_token(raw)
            else:
                digest = (c.token_sha256 or "").lower()
                if len(digest) != 64:
                    warnings.append(f"client {c.id!r} disabled: token_sha256 must be 64 hex characters")
                    continue
            identity = ClientIdentity(
                client_id=c.id,
                role=c.role,
                permissions=ROLE_PERMISSIONS[c.role],
                label=c.label or c.id,
                home_entities=frozenset(c.home_entities) if c.home_entities is not None else None,
                memory_scopes=frozenset(c.memory_scopes),
            )
            store.add(digest, identity)
        return store, warnings

    def role_permissions(self, role: str) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[role]


def default_config_path() -> Path:
    env = os.environ.get("COMPANION_CONFIG")
    if env:
        return Path(env)
    root = repo_root()
    local = root / "config" / "local.yaml"
    return local if local.exists() else root / "config" / "example.yaml"


def load_config(path: str | Path | None = None, *, env_file: str | Path | None = None) -> AppConfig:
    """Load and validate configuration. Raises ``ConfigError`` with a readable message."""
    root = repo_root()
    env_path = Path(env_file) if env_file else Path(os.environ.get("COMPANION_ENV_FILE", root / ".env"))
    load_env_file(env_path)

    cfg_path = Path(path) if path else default_config_path()
    if not cfg_path.is_file():
        raise ConfigError(f"config file not found: {cfg_path}")
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse {cfg_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{cfg_path} must contain a mapping at the top level")
    raw.pop("source_path", None)
    raw.pop("base_dir", None)
    try:
        cfg = AppConfig.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError formats nicely via str()
        raise ConfigError(f"invalid configuration in {cfg_path}:\n{exc}") from exc
    cfg.source_path = cfg_path.resolve()
    cfg.base_dir = root
    return cfg


def config_summary(cfg: AppConfig) -> dict:
    """A redacted view suitable for ``/v1/settings`` and logs."""
    return {
        "instance": cfg.instance.model_dump(mode="json"),
        "llm": {"provider": cfg.llm.provider, "model": cfg.llm.model or None, "base_url": cfg.llm.base_url},
        "home": {"provider": cfg.home.provider, "allowed_entities": len(cfg.home.allowed_entities)},
        "vault": {"mode": cfg.vault.mode},
        "stt": {"provider": cfg.stt.provider, "model": cfg.stt.model},
        "tts": {"provider": cfg.tts.provider, "voice": cfg.tts.voice},
        "wake_word": {"enabled": cfg.wake_word.enabled, "provider": cfg.wake_word.provider},
        "weather": {"provider": cfg.weather.provider, "location_name": cfg.weather.location_name},
        "email": {"provider": cfg.email.provider},
        "mtg": {"provider": cfg.mtg.provider},
        "robotics": {"mode": cfg.robotics.mode},
        "clients": [{"id": c.id, "role": c.role, "label": c.label} for c in cfg.clients],
        "config_path": str(cfg.source_path) if cfg.source_path else None,
    }
