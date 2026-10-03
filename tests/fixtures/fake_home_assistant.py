"""A fake Home Assistant REST server for tests (httpx.MockTransport handler)."""

from __future__ import annotations

import json
from typing import Any

import httpx

TOKEN = "ha-long-lived-token-for-tests"


class FakeHA:
    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {
            "light.desk_lamp": {"state": "off", "attributes": {"friendly_name": "Desk lamp", "supported_color_modes": ["color_temp", "hs"], "brightness": None}},
            "light.hall": {"state": "on", "attributes": {"friendly_name": "Hall", "supported_color_modes": ["onoff"]}},
            "switch.heater": {"state": "off", "attributes": {"friendly_name": "Heater"}},
            "scene.study": {"state": "2026-01-01T00:00:00+00:00", "attributes": {"friendly_name": "Study lighting"}},
            "camera.front_door": {"state": "idle", "attributes": {"friendly_name": "Front door", "supported_features": 2}},
            "sensor.outside_temp": {"state": "11.2", "attributes": {"friendly_name": "Outside temperature", "unit_of_measurement": "°C"}},
            "lock.front": {"state": "locked", "attributes": {"friendly_name": "Front door lock"}},
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.snapshot_requests = 0

    def _state(self, eid: str) -> dict[str, Any]:
        s = self.states[eid]
        return {"entity_id": eid, "state": s["state"], "attributes": s["attributes"], "last_changed": "2026-10-03T10:00:00+00:00", "last_updated": "2026-10-03T10:00:00+00:00"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"message": "Unauthorized"})
        path = request.url.path
        if path == "/api/":
            return httpx.Response(200, json={"message": "API running."})
        if path == "/api/config":
            return httpx.Response(200, json={"version": "2026.9.1", "location_name": "Test Home"})
        if path == "/api/states":
            return httpx.Response(200, json=[self._state(e) for e in self.states])
        if path.startswith("/api/states/"):
            eid = path.split("/", 3)[3]
            return httpx.Response(200, json=self._state(eid)) if eid in self.states else httpx.Response(404, json={"message": "Entity not found."})
        if path.startswith("/api/services/"):
            _, _, _, domain, service = path.split("/", 4)
            body = json.loads(request.content or b"{}")
            self.calls.append((f"{domain}.{service}", body))
            eid = body.get("entity_id")
            if eid in self.states and domain != "scene":
                if service == "turn_on":
                    self.states[eid]["state"] = "on"
                    if "brightness_pct" in body:
                        self.states[eid]["attributes"]["brightness"] = round(body["brightness_pct"] * 2.55)
                elif service == "turn_off":
                    self.states[eid]["state"] = "off"
                return httpx.Response(200, json=[self._state(eid)])
            return httpx.Response(200, json=[])
        if path.startswith("/api/camera_proxy_stream/"):
            return httpx.Response(200, content=b"--frameboundary\r\nContent-Type: image/jpeg\r\n\r\nFRAME1\r\n--frameboundary\r\n", headers={"content-type": "multipart/x-mixed-replace; boundary=--frameboundary"})
        if path.startswith("/api/camera_proxy/"):
            self.snapshot_requests += 1
            return httpx.Response(200, content=b"\xff\xd8JPEGDATA\xff\xd9", headers={"content-type": "image/jpeg"})
        return httpx.Response(404, json={"message": "not found"})
