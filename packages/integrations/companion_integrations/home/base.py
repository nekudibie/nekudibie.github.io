from __future__ import annotations

from typing import Any, Protocol

from companion_contracts.health import DependencyStatus
from companion_contracts.home import CameraView, Entity, HomeCommandResult

ACTIONS_BY_DOMAIN: dict[str, set[str]] = {
    "light": {"turn_on", "turn_off", "toggle"},
    "switch": {"turn_on", "turn_off", "toggle"},
    "input_boolean": {"turn_on", "turn_off", "toggle"},
    "scene": {"activate"},
    "camera": set(),
    "sensor": set(),
    "binary_sensor": set(),
}


class HomeProvider(Protocol):
    name: str
    is_fixture: bool

    async def list_entities(self) -> list[Entity]: ...
    async def get_entity(self, entity_id: str) -> Entity: ...
    async def call(self, entity_id: str, action: str, params: dict[str, Any]) -> HomeCommandResult: ...
    async def camera_snapshot(self, entity_id: str) -> tuple[bytes, str]: ...
    async def camera_view(self, entity_id: str) -> CameraView: ...
    async def health(self) -> DependencyStatus: ...


def domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]
