from __future__ import annotations

from tests.conftest import ADMIN, DESK, GUEST, ROVER, auth, new_conversation, sse, text_of


def test_unauthenticated_and_bad_tokens_are_rejected(client):
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/v1/memory/notes").status_code == 401
    assert client.post("/v1/conversations", json={}).status_code == 401
    assert client.get("/v1/home/entities").status_code == 401
    # health endpoints are public but reveal nothing private
    assert client.get("/healthz").status_code == 200
    assert "tokens" not in client.get("/readyz").text


def test_roles_get_different_tools(client):
    desk = client.get("/v1/me", headers=DESK).json()
    rover = client.get("/v1/me", headers=ROVER).json()
    guest = client.get("/v1/me", headers=GUEST).json()
    assert "home_control" in desk["tools"] and "memory_save" in desk["tools"]
    assert "home_control" not in rover["tools"] and "memory_save" not in rover["tools"]
    assert guest["tools"] == ["clock_now"]


def test_cross_client_conversation_denied(client):
    cid = new_conversation(client, DESK)
    assert client.get(f"/v1/conversations/{cid}", headers=ROVER).status_code == 403
    r = client.post(f"/v1/conversations/{cid}/messages", json={"content": "hi"}, headers=ROVER)
    assert r.status_code == 403
    assert client.post(f"/v1/conversations/{cid}/cancel", headers=ROVER).status_code == 403
    # the owner/admin role may inspect any conversation; another desk-level client may not
    assert client.get(f"/v1/conversations/{cid}", headers=ADMIN).status_code == 200
    assert client.get(f"/v1/conversations/{cid}", headers=auth("limited-desk-token-0123456789")).status_code == 403


def test_permission_denied_on_memory_and_home_endpoints(client):
    assert client.post("/v1/memory/notes", json={"text": "x"}, headers=GUEST).status_code == 403
    assert client.get("/v1/memory/notes", headers=GUEST).status_code == 403
    assert client.post("/v1/home/entities/light.desk_lamp/command", json={"action": "turn_on"}, headers=ROVER).status_code == 403
    d = client.post("/v1/memory/notes", json={"text": "owner note"}, headers=DESK).json()
    # rover may read memory but only the shared scope: owner notes are invisible to it
    assert client.get(f"/v1/memory/documents/{d['id']}", headers=ROVER).status_code == 404
    assert client.post("/v1/memory/search", json={"query": "owner note"}, headers=ROVER).json()["hits"] == []
    # carried/desk may not delete unless role allows; rover definitely not
    assert client.delete(f"/v1/memory/documents/{d['id']}", headers=ROVER).status_code == 403


def test_entity_allowlist_per_client(client):
    limited = auth("limited-desk-token-0123456789")
    ents = client.get("/v1/home/entities", headers=limited).json()
    assert [e["entity_id"] for e in ents] == ["light.desk_lamp"]
    r = client.post("/v1/home/entities/light.study_ceiling/command", json={"action": "turn_on"}, headers=limited)
    assert r.status_code == 403
    cid = new_conversation(client, limited)
    out = text_of(sse(client, cid, "turn on the study ceiling", headers=limited))
    assert "don't know a device" in out and "Desk lamp" in out
    ok = client.post("/v1/home/entities/light.desk_lamp/command", json={"action": "turn_on", "brightness_pct": 40}, headers=limited)
    assert ok.status_code == 200 and ok.json()["is_fixture"] is True


def test_guest_can_converse_but_not_use_memory(client):
    cid = new_conversation(client, GUEST)
    events = sse(client, cid, "What did we decide about the Lantern project?", headers=GUEST)
    # the fixture model only offers memory_search when the tool is available; the guest never gets it
    assert not any(t == "tool_call" for t, _ in events)
    assert "fixture model" in text_of(events)
