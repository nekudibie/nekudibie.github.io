from __future__ import annotations

from companion_integrations.llm.fixture import ScriptedProvider

from tests.conftest import ADMIN, DESK, GUEST, ROVER, new_conversation, sse


def test_rover_client_commands_within_limits_and_watchdog_stops(client):
    st = client.get("/v1/robot/status", headers=ROVER).json()
    assert st["mode"] == "simulated" and st["state"] == "idle" and "no motor output" in st["note"]
    r = client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.2, "duration_s": 3}, headers=ROVER)
    assert r.status_code == 200 and r.json()["state"] == "moving" and r.json()["active_command"]["client_id"] == "rover1"
    too_fast = client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.9, "duration_s": 1}, headers=ROVER)
    assert too_fast.status_code == 422 and "exceeds the limit" in too_fast.text
    unbounded = client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.1, "duration_s": 1, "pwm": 255}, headers=ROVER)
    assert unbounded.status_code == 422  # no such field: raw outputs do not exist
    # the client goes quiet: the admin tick advances the simulation by a second, longer than the watchdog
    st = client.post("/v1/robot/sim/tick", headers=ADMIN).json()
    assert st["state"] == "stopped_watchdog"


def test_stop_estop_and_reset_authority(client):
    client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.1, "duration_s": 2}, headers=ROVER)
    assert client.post("/v1/robot/stop", headers=ROVER).json()["state"] == "idle"
    assert client.post("/v1/robot/estop", headers=DESK).json()["estop_latched"] is True
    denied = client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.1, "duration_s": 1}, headers=ROVER)
    assert denied.status_code == 409 and "emergency stop" in denied.text
    assert client.post("/v1/robot/reset", headers=ROVER).json()["estop_latched"] is False
    assert client.post("/v1/robot/sim/link?value=false", headers=ADMIN).json()["state"] == "stopped_link"
    assert client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.1, "duration_s": 1}, headers=ROVER).status_code == 409
    client.post("/v1/robot/sim/link?value=true", headers=ADMIN)
    assert client.post("/v1/robot/sim/bumper?value=true", headers=ADMIN).json()["state"] == "stopped_bumper"
    assert client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.1, "duration_s": 1}, headers=ROVER).status_code == 409
    assert client.post("/v1/robot/command", json={"kind": "move", "linear_mps": -0.1, "duration_s": 1}, headers=ROVER).status_code == 200  # backing off is allowed


def test_unauthorised_clients_cannot_move_it(client):
    assert client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.1, "duration_s": 1}, headers=GUEST).status_code == 403
    assert client.get("/v1/robot/status", headers=GUEST).status_code == 403
    assert client.post("/v1/robot/command", json={"kind": "move", "linear_mps": 0.1, "duration_s": 1}).status_code == 401
    assert client.post("/v1/robot/sim/tick", headers=ROVER).status_code == 403  # sensor injection is admin-only


def test_model_requests_are_bounded_and_permission_checked(make_client):
    llm = ScriptedProvider([
        [{"name": "robot_command", "arguments": {"action": "move", "direction": "forward", "distance_m": 50}}],  # beyond schema (max 2.0) -> invalid
        [{"name": "robot_command", "arguments": {"action": "move", "direction": "forward", "distance_m": 1.0}}],
        ["moving a little"],
        [{"name": "robot_command", "arguments": {"action": "move", "direction": "forward", "distance_m": 0.5}}],
        ["denied"],
    ])
    client = make_client(llm=llm)
    cid = new_conversation(client, ROVER)
    events = sse(client, cid, "go forward a lot", headers=ROVER)
    calls = [d for t, d in events if t == "tool_call"]
    assert calls[0]["status"] == "invalid" and calls[1]["status"] == "validated"
    st = client.get("/v1/robot/status", headers=ROVER).json()
    assert st["active_command"] is None or st["active_command"]["linear_mps"] <= 0.3
    # the desk may also command it, but a guest's model turn is refused by the gateway
    gcid = new_conversation(client, GUEST)
    events = sse(client, gcid, "drive into the kitchen", headers=GUEST)
    call = [d for t, d in events if t == "tool_call"][0]
    assert call["status"] == "denied" and "robot.command" in call["reason"]


def test_disabled_mode_has_no_robot(cfg, make_client):
    cfg.robotics.mode = "disabled"
    client = make_client()
    assert client.get("/v1/robot/status", headers=ROVER).status_code == 501
    tools = {t["name"]: t for t in client.get("/v1/tools", headers=ROVER).json()["tools"]}
    assert tools["robot_command"]["enabled"] is False
