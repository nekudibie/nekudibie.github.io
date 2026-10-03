from __future__ import annotations

import httpx
import pytest

from companion_core.errors import UpstreamError, UpstreamUnavailable
from companion_integrations.home.home_assistant import HomeAssistantProvider, capabilities_from_state
from tests.conftest import ADMIN, DESK, ROVER, new_conversation, sse, text_of
from tests.fixtures.fake_home_assistant import TOKEN, FakeHA


def provider(fake: FakeHA, token: str = TOKEN) -> HomeAssistantProvider:
    return HomeAssistantProvider("http://ha.test:8123", token, transport=httpx.MockTransport(fake.handler), states_cache_s=0)


def test_capabilities_come_from_real_attributes():
    assert capabilities_from_state("light.a", {"supported_color_modes": ["onoff"]}).brightness is False
    c = capabilities_from_state("light.b", {"supported_color_modes": ["color_temp", "hs"]})
    assert c.brightness and c.color_temp and c.rgb_color and c.on_off
    assert capabilities_from_state("camera.c", {"supported_features": 2}).stream is True
    assert capabilities_from_state("camera.d", {}).stream is False and capabilities_from_state("camera.d", {}).snapshot is True
    assert capabilities_from_state("scene.e", {}).activate is True
    assert capabilities_from_state("lock.f", {}).on_off is False


@pytest.mark.asyncio
async def test_adapter_calls_documented_endpoints():
    fake = FakeHA()
    p = provider(fake)
    ents = await p.list_entities()
    assert {e.entity_id for e in ents} >= {"light.desk_lamp", "scene.study", "camera.front_door"}
    lamp = next(e for e in ents if e.entity_id == "light.desk_lamp")
    assert lamp.friendly_name == "Desk lamp" and lamp.capabilities.brightness and not lamp.is_fixture
    res = await p.call("light.desk_lamp", "turn_on", {"brightness_pct": 40})
    assert fake.calls[-1] == ("light.turn_on", {"entity_id": "light.desk_lamp", "brightness_pct": 40})
    assert res.new_state == "on" and res.provider == "home_assistant"
    res = await p.call("scene.study", "activate", {})
    assert fake.calls[-1] == ("scene.turn_on", {"entity_id": "scene.study"}) and res.new_state == "activated"
    data, ctype = await p.camera_snapshot("camera.front_door")
    assert data.startswith(b"\xff\xd8") and ctype == "image/jpeg"
    ctype, gen = await p.camera_stream("camera.front_door")
    body = b"".join([chunk async for chunk in gen])
    assert ctype.startswith("multipart/x-mixed-replace") and b"FRAME1" in body
    h = await p.health()
    assert h.status == "ok" and "2026.9.1" in h.detail


@pytest.mark.asyncio
async def test_adapter_error_mapping():
    fake = FakeHA()
    bad = provider(fake, token="wrong")
    with pytest.raises(UpstreamError, match="rejected the access token"):
        await bad.list_entities()
    assert (await bad.health()).status == "down"

    def down(request):
        raise httpx.ConnectError("no route")

    p = HomeAssistantProvider("http://ha.test:8123", TOKEN, transport=httpx.MockTransport(down))
    with pytest.raises(UpstreamUnavailable):
        await p.list_entities()
    assert (await p.health()).status == "down"


def test_api_with_home_assistant_enforces_explicit_allowlist(cfg, make_client):
    fake = FakeHA()
    cfg.home.provider = "home_assistant"
    cfg.home.allowed_entities = ["light.desk_lamp", "scene.study", "camera.front_door"]
    cfg.home.scenes = {"study lighting": "scene.study"}
    cfg.home.cameras = {"front door": "camera.front_door"}
    client = make_client(home=provider(fake))

    ents = client.get("/v1/home/entities", headers=DESK).json()
    assert {e["entity_id"] for e in ents} == {"light.desk_lamp", "scene.study", "camera.front_door"}
    assert all(e["is_fixture"] is False for e in ents)
    # heater and lock exist in HA but are not allowlisted: invisible and uncontrollable
    assert client.post("/v1/home/entities/switch.heater/command", json={"action": "turn_on"}, headers=DESK).status_code == 403
    assert client.post("/v1/home/entities/lock.front/command", json={"action": "turn_on"}, headers=DESK).status_code == 403
    assert fake.calls == []
    # the admin discovery view shows everything with the allowed flag, for building the list
    disc = client.get("/v1/home/discover", headers=ADMIN).json()
    assert disc["is_fixture"] is False and {e["entity_id"]: e["allowed"] for e in disc["entities"]}["switch.heater"] is False
    assert client.get("/v1/home/discover", headers=DESK).status_code == 403

    cid = new_conversation(client)
    out = text_of(sse(client, cid, "turn on the desk lamp"))
    assert "Desk lamp turned on" in out and "fixture" not in out
    assert fake.calls[-1][0] == "light.turn_on"
    assert "Study lighting activated" in text_of(sse(client, cid, "set study lighting"))
    assert fake.calls[-1] == ("scene.turn_on", {"entity_id": "scene.study"})
    out = text_of(sse(client, cid, "turn on the heater"))
    assert "don't know a device" in out and fake.calls[-1][0] == "scene.turn_on"

    snap = client.get("/v1/home/cameras/camera.front_door/snapshot", headers=DESK)
    assert snap.status_code == 200 and snap.headers["content-type"] == "image/jpeg" and snap.headers["x-companion-fixture"] == "false"
    assert client.get("/v1/home/cameras/camera.front_door/snapshot", headers=ROVER).status_code == 403
    view = client.get("/v1/home/cameras/camera.front_door/view", headers=DESK).json()
    assert view["stream_kind"] == "mjpeg" and view["is_fixture"] is False

    # stream tickets: short-lived, bound to client + camera, usable without headers by <img>
    t = client.post("/v1/home/cameras/camera.front_door/stream-ticket", headers=DESK).json()
    assert t["expires_in_s"] > 0
    with client.stream("GET", f"/v1/home/cameras/camera.front_door/stream?ticket={t['ticket']}") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("multipart/x-mixed-replace")
        assert b"FRAME1" in b"".join(r.iter_bytes())
    assert client.get("/v1/home/cameras/camera.front_door/stream?ticket=bogus").status_code == 401
    assert client.get(f"/v1/home/cameras/light.desk_lamp/stream?ticket={t['ticket']}").status_code == 403


def test_home_assistant_model_tool_path_is_allowlisted_too(cfg, make_client):
    from companion_integrations.llm.fixture import ScriptedProvider

    fake = FakeHA()
    cfg.home.provider = "home_assistant"
    cfg.home.allowed_entities = ["light.desk_lamp"]
    llm = ScriptedProvider([[{"name": "home_control", "arguments": {"entity_id": "lock.front", "action": "turn_on"}}], ["refused"]])
    client = make_client(home=provider(fake), llm=llm)
    cid = new_conversation(client)
    events = sse(client, cid, "unlock the front door")
    call = [d for t, d in events if t == "tool_call"][0]
    assert call["status"] == "denied" and "allowlist" in call["reason"]
    assert fake.calls == []
