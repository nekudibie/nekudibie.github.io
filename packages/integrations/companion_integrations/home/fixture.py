"""A clearly labelled fixture home: a few lights, a scene and a camera placeholder."""

from __future__ import annotations

import time
from typing import Any

from companion_contracts.health import DependencyStatus
from companion_contracts.home import CameraView, Entity, EntityCapabilities, HomeCommandResult
from companion_core.clock import iso, now_utc
from companion_core.errors import NotFound, ValidationFailed

from .base import ACTIONS_BY_DOMAIN, domain_of

_PLACEHOLDER_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>
<rect width='100%' height='100%' fill='#1f2933'/>
<text x='50%' y='45%' fill='#f8b84e' font-family='sans-serif' font-size='28' text-anchor='middle'>FIXTURE CAMERA</text>
<text x='50%' y='58%' fill='#cbd2d9' font-family='sans-serif' font-size='18' text-anchor='middle'>Not a live feed. {name} — {ts}</text>
</svg>"""


class FixtureHomeProvider:
    name = "fixture"
    is_fixture = True

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {
            "light.desk_lamp": {"friendly_name": "Desk lamp", "state": "off", "brightness": 0, "supports": ["brightness", "color_temp"]},
            "light.study_ceiling": {"friendly_name": "Study ceiling", "state": "on", "brightness": 180, "supports": ["brightness"]},
            "switch.monitor_plug": {"friendly_name": "Monitor plug", "state": "on", "supports": []},
            "scene.study": {"friendly_name": "Study lighting", "state": "scening", "supports": []},
            "scene.relax": {"friendly_name": "Relax", "state": "scening", "supports": []},
            "camera.front_door": {"friendly_name": "Front door", "state": "idle", "supports": []},
            "sensor.study_temperature": {"friendly_name": "Study temperature", "state": "20.5", "unit": "°C", "supports": []},
        }
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _entity(self, entity_id: str) -> Entity:
        s = self._state.get(entity_id)
        if s is None:
            raise NotFound(f"unknown entity {entity_id}")
        dom = domain_of(entity_id)
        caps = EntityCapabilities(
            on_off=dom in {"light", "switch", "input_boolean"},
            brightness="brightness" in s["supports"],
            color_temp="color_temp" in s["supports"],
            activate=dom == "scene",
            snapshot=dom == "camera",
            stream=False,
        )
        attrs = {k: v for k, v in s.items() if k not in {"state", "supports"}}
        return Entity(
            entity_id=entity_id, domain=dom, friendly_name=s["friendly_name"], state=s["state"], attributes=attrs,
            capabilities=caps, last_changed=iso(now_utc()), provider=self.name, is_fixture=True,
        )

    async def list_entities(self) -> list[Entity]:
        return [self._entity(e) for e in self._state]

    async def get_entity(self, entity_id: str) -> Entity:
        return self._entity(entity_id)

    async def call(self, entity_id: str, action: str, params: dict[str, Any]) -> HomeCommandResult:
        ent = self._entity(entity_id)
        allowed = ACTIONS_BY_DOMAIN.get(ent.domain, set())
        if action not in allowed:
            raise ValidationFailed(f"{action} is not supported for {entity_id} (domain {ent.domain})")
        s = self._state[entity_id]
        self.calls.append((entity_id, action, dict(params)))
        if action == "activate":
            if entity_id == "scene.study":
                self._state["light.desk_lamp"].update(state="on", brightness=200)
                self._state["light.study_ceiling"].update(state="on", brightness=255)
            elif entity_id == "scene.relax":
                self._state["light.desk_lamp"].update(state="on", brightness=60)
                self._state["light.study_ceiling"].update(state="off", brightness=0)
            return HomeCommandResult(entity_id=entity_id, action=action, ok=True, new_state="activated", provider=self.name, is_fixture=True, message="fixture scene applied")
        if action == "toggle":
            action = "turn_off" if s["state"] == "on" else "turn_on"
        if action == "turn_on":
            s["state"] = "on"
            if params.get("brightness_pct") is not None and ent.capabilities.brightness:
                s["brightness"] = round(params["brightness_pct"] * 255 / 100)
            elif s.get("brightness") == 0 and ent.capabilities.brightness:
                s["brightness"] = 255
        elif action == "turn_off":
            s["state"] = "off"
            if ent.capabilities.brightness:
                s["brightness"] = 0
        return HomeCommandResult(entity_id=entity_id, action=action, ok=True, new_state=s["state"], provider=self.name, is_fixture=True, message="fixture state changed")

    async def camera_snapshot(self, entity_id: str) -> tuple[bytes, str]:
        ent = self._entity(entity_id)
        if ent.domain != "camera":
            raise ValidationFailed(f"{entity_id} is not a camera")
        svg = _PLACEHOLDER_SVG.format(name=ent.friendly_name, ts=time.strftime("%H:%M:%S"))
        return svg.encode("utf-8"), "image/svg+xml"

    async def camera_view(self, entity_id: str) -> CameraView:
        ent = self._entity(entity_id)
        if ent.domain != "camera":
            raise ValidationFailed(f"{entity_id} is not a camera")
        return CameraView(
            entity_id=entity_id, friendly_name=ent.friendly_name,
            snapshot_url=f"/v1/home/cameras/{entity_id}/snapshot", stream_kind="none", stream_url=None,
            provider=self.name, is_fixture=True, note="Fixture placeholder image. No live feed is configured.",
        )

    async def health(self) -> DependencyStatus:
        return DependencyStatus(name="home", status="fixture", detail="fixture home: simulated entities, not real devices")
