from __future__ import annotations

import pytest
from companion_integrations.home.fixture import FixtureHomeProvider

from tests.conftest import DESK, new_conversation, sse, text_of


@pytest.mark.parametrize(
    "phrase,entity,action,extra",
    [
        ("Turn on the desk lamp", "light.desk_lamp", "turn_on", {}),
        ("switch the desk lamp off", "light.desk_lamp", "turn_off", {}),
        ("turn off monitor plug please", "switch.monitor_plug", "turn_off", {}),
        ("dim the desk lamp to 30%", "light.desk_lamp", "turn_on", {"brightness_pct": 30}),
        ("Set study lighting", "scene.study", "activate", {}),
        ("activate the relax scene", "scene.relax", "activate", {}),
        ("turn on study lighting", "scene.study", "activate", {}),
    ],
)
def test_home_phrases_route_deterministically(make_client, phrase, entity, action, extra):
    home = FixtureHomeProvider()
    client = make_client(home=home)
    cid = new_conversation(client)
    events = sse(client, cid, phrase)
    done = [d for t, d in events if t == "done"][0]
    assert done["route"] == "deterministic"
    assert home.calls[-1][0] == entity and home.calls[-1][1] == action
    for k, v in extra.items():
        assert home.calls[-1][2][k] == v


def test_ambiguous_name_is_reported_not_guessed(make_client):
    home = FixtureHomeProvider()
    client = make_client(home=home)
    cid = new_conversation(client)
    out = text_of(sse(client, cid, "turn on the study"))
    assert "don't know a device" in out and home.calls == []


def test_camera_route_emits_ui_event(client):
    cid = new_conversation(client)
    events = sse(client, cid, "show me the front door")
    ui = [d for t, d in events if t == "ui"]
    assert ui and ui[0]["action"] == "show_camera" and ui[0]["payload"]["is_fixture"] is True
    assert "not a live feed" in text_of(events)


def test_show_notes_is_not_hijacked_by_camera_route(client):
    cid = new_conversation(client)
    events = sse(client, cid, "show me my notes")
    assert not any(t == "ui" for t, _ in events)


def test_stop_and_mute_are_handled_without_model(client):
    cid = new_conversation(client)
    events = sse(client, cid, "mute the microphone")
    ui = [d for t, d in events if t == "ui"][0]
    assert ui["payload"] == {"mute": True, "software_only": True}
    assert "hardware switch" in text_of(events)
    assert text_of(sse(client, cid, "stop")) == "Nothing to stop."
    assert text_of(sse(client, cid, "unmute")) == "Microphone unmuted."


def test_home_disabled_falls_through_cleanly(make_client):
    client = make_client(home=None)
    cid = new_conversation(client)
    events = sse(client, cid, "turn on the desk lamp")
    assert [d for t, d in events if t == "done"][0]["route"] == "fixture_llm"
    assert client.get("/v1/home/entities", headers=DESK).status_code == 501
    tools = client.get("/v1/tools", headers=DESK).json()["tools"]
    hc = next(t for t in tools if t["name"] == "home_control")
    assert hc["enabled"] is False and "disabled" in hc["disabled_reason"]
