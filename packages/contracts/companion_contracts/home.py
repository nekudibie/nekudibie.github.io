"""Home control schemas (Home Assistant or fixture)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EntityCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on_off: bool = False
    brightness: bool = False
    color_temp: bool = False
    rgb_color: bool = False
    activate: bool = False  # scenes
    snapshot: bool = False  # cameras
    stream: bool = False  # cameras with a stream source


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    domain: str
    friendly_name: str
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    capabilities: EntityCapabilities = Field(default_factory=EntityCapabilities)
    last_changed: str | None = None
    provider: str
    is_fixture: bool


class HomeCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    action: str
    ok: bool
    new_state: str | None = None
    provider: str
    is_fixture: bool
    message: str = ""


class CameraView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    friendly_name: str
    snapshot_url: str  # API-relative; the API proxies HA with server-side credentials
    stream_kind: Literal["mjpeg", "hls", "none"]
    stream_url: str | None = None
    provider: str
    is_fixture: bool
    note: str = ""
