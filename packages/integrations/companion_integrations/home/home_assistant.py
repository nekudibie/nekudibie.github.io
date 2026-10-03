"""Home Assistant REST adapter.

Verified against the REST API reference (docs/SOURCES.md): ``Authorization: Bearer``,
``GET /api/``, ``GET /api/config``, ``GET /api/states``, ``GET /api/states/<entity_id>``,
``POST /api/services/<domain>/<service>`` (body carries ``entity_id`` and service data),
``GET /api/camera_proxy/<entity_id>`` (still image) and
``GET /api/camera_proxy_stream/<entity_id>`` (multipart MJPEG, from HA core's camera views).

Capabilities are derived from the entity's real attributes (``supported_color_modes`` for
lights, ``supported_features`` for cameras), never assumed.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from companion_contracts.health import DependencyStatus
from companion_contracts.home import CameraView, Entity, EntityCapabilities, HomeCommandResult
from companion_core.errors import NotFound, UpstreamError, UpstreamUnavailable, ValidationFailed
from companion_core.logging import get_logger

from .base import ACTIONS_BY_DOMAIN, domain_of

log = get_logger(__name__)

CAMERA_FEATURE_STREAM = 2  # homeassistant.components.camera.CameraEntityFeature.STREAM
_COLOUR_MODES = {"hs", "rgb", "rgbw", "rgbww", "xy"}
_BRIGHTNESS_MODES = _COLOUR_MODES | {"brightness", "color_temp", "white"}


def capabilities_from_state(entity_id: str, attrs: dict[str, Any]) -> EntityCapabilities:
    dom = domain_of(entity_id)
    if dom == "light":
        modes = set(attrs.get("supported_color_modes") or [])
        return EntityCapabilities(
            on_off=True,
            brightness=bool(modes & _BRIGHTNESS_MODES),
            color_temp="color_temp" in modes,
            rgb_color=bool(modes & _COLOUR_MODES),
        )
    if dom in {"switch", "input_boolean"}:
        return EntityCapabilities(on_off=True)
    if dom == "scene":
        return EntityCapabilities(activate=True)
    if dom == "camera":
        feats = int(attrs.get("supported_features") or 0)
        return EntityCapabilities(snapshot=True, stream=bool(feats & CAMERA_FEATURE_STREAM))
    return EntityCapabilities()


class HomeAssistantProvider:
    name = "home_assistant"
    is_fixture = False

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        states_cache_s: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=3.0, read=timeout_s, write=timeout_s, pool=3.0),
            transport=transport,
        )
        self._cache: tuple[float, list[dict[str, Any]]] | None = None
        self._cache_s = states_cache_s

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- transport helpers ----------------------------------------------
    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            r = await self._client.request(method, path, **kw)
        except httpx.TimeoutException as exc:
            raise UpstreamUnavailable(f"Home Assistant timed out ({exc.__class__.__name__})") from exc
        except httpx.TransportError as exc:
            raise UpstreamUnavailable(f"Home Assistant unreachable at {self.base_url} ({exc.__class__.__name__})") from exc
        if r.status_code == 401:
            raise UpstreamError("Home Assistant rejected the access token (401)")
        if r.status_code == 404:
            raise NotFound(f"Home Assistant: {path} not found")
        if r.status_code >= 400:
            raise UpstreamError(f"Home Assistant returned {r.status_code} for {method} {path}: {r.text[:200]}")
        return r

    async def _states(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._cache and now - self._cache[0] < self._cache_s:
            return self._cache[1]
        r = await self._request("GET", "/api/states")
        data = r.json()
        if not isinstance(data, list):
            raise UpstreamError("Home Assistant /api/states returned an unexpected payload")
        self._cache = (now, data)
        return data

    def invalidate(self) -> None:
        self._cache = None

    @staticmethod
    def _to_entity(s: dict[str, Any]) -> Entity:
        eid = s["entity_id"]
        attrs = s.get("attributes") or {}
        return Entity(
            entity_id=eid,
            domain=domain_of(eid),
            friendly_name=str(attrs.get("friendly_name") or eid),
            state=str(s.get("state")),
            attributes=attrs,
            capabilities=capabilities_from_state(eid, attrs),
            last_changed=s.get("last_changed"),
            provider="home_assistant",
            is_fixture=False,
        )

    # -- HomeProvider ----------------------------------------------------
    async def list_entities(self) -> list[Entity]:
        return [self._to_entity(s) for s in await self._states()]

    async def get_entity(self, entity_id: str) -> Entity:
        r = await self._request("GET", f"/api/states/{entity_id}")
        return self._to_entity(r.json())

    async def call(self, entity_id: str, action: str, params: dict[str, Any]) -> HomeCommandResult:
        dom = domain_of(entity_id)
        if action not in ACTIONS_BY_DOMAIN.get(dom, set()):
            raise ValidationFailed(f"{action} is not supported for domain {dom}")
        service = "turn_on" if action == "activate" else action
        body: dict[str, Any] = {"entity_id": entity_id}
        if action in {"turn_on", "activate"}:
            for key in ("brightness_pct", "color_temp_kelvin", "rgb_color"):
                if params.get(key) is not None:
                    body[key] = params[key]
        r = await self._request("POST", f"/api/services/{dom}/{service}", json=body)
        self.invalidate()
        new_state: str | None = None
        try:
            for changed in r.json() or []:
                if isinstance(changed, dict) and changed.get("entity_id") == entity_id:
                    new_state = str(changed.get("state"))
        except ValueError:
            pass
        if new_state is None and dom != "scene":
            try:
                new_state = (await self.get_entity(entity_id)).state
            except (NotFound, UpstreamError, UpstreamUnavailable):
                new_state = None
        return HomeCommandResult(
            entity_id=entity_id, action=action, ok=True, new_state=new_state if dom != "scene" else "activated",
            provider=self.name, is_fixture=False, message=f"{dom}.{service} called",
        )

    async def camera_snapshot(self, entity_id: str) -> tuple[bytes, str]:
        if domain_of(entity_id) != "camera":
            raise ValidationFailed(f"{entity_id} is not a camera")
        r = await self._request("GET", f"/api/camera_proxy/{entity_id}")
        return r.content, r.headers.get("content-type", "image/jpeg")

    async def camera_stream(self, entity_id: str) -> tuple[str, AsyncIterator[bytes]]:
        """Proxy HA's MJPEG stream. Returns (content_type, byte chunks)."""
        if domain_of(entity_id) != "camera":
            raise ValidationFailed(f"{entity_id} is not a camera")
        req = self._client.build_request("GET", f"/api/camera_proxy_stream/{entity_id}", timeout=httpx.Timeout(connect=3.0, read=None, write=None, pool=3.0))
        try:
            resp = await self._client.send(req, stream=True)
        except httpx.TransportError as exc:
            raise UpstreamUnavailable(f"Home Assistant unreachable ({exc.__class__.__name__})") from exc
        if resp.status_code != 200:
            await resp.aclose()
            if resp.status_code == 404:
                raise NotFound(f"camera {entity_id} not found")
            raise UpstreamError(f"Home Assistant stream returned {resp.status_code}")
        ctype = resp.headers.get("content-type", "multipart/x-mixed-replace")

        async def gen() -> AsyncIterator[bytes]:
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()

        return ctype, gen()

    async def camera_view(self, entity_id: str) -> CameraView:
        ent = await self.get_entity(entity_id)
        if ent.domain != "camera":
            raise ValidationFailed(f"{entity_id} is not a camera")
        return CameraView(
            entity_id=entity_id, friendly_name=ent.friendly_name,
            snapshot_url=f"/v1/home/cameras/{entity_id}/snapshot",
            stream_kind="mjpeg", stream_url=f"/v1/home/cameras/{entity_id}/stream",
            provider=self.name, is_fixture=False,
            note="Live via Home Assistant (MJPEG proxy). HLS/WebRTC not yet wired." + ("" if ent.capabilities.stream else " Camera reports no native stream; HA generates MJPEG from stills."),
        )

    async def health(self) -> DependencyStatus:
        started = time.monotonic()
        try:
            r = await self._request("GET", "/api/config")
            cfg = r.json()
            latency = int((time.monotonic() - started) * 1000)
            return DependencyStatus(
                name="home", status="ok", latency_ms=latency,
                detail=f"Home Assistant {cfg.get('version', '?')} at {self.base_url} ({cfg.get('location_name', '')})",
            )
        except (UpstreamError, UpstreamUnavailable, NotFound, ValueError) as exc:
            return DependencyStatus(name="home", status="down", detail=str(exc)[:160], latency_ms=int((time.monotonic() - started) * 1000))
