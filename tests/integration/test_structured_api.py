from __future__ import annotations

import httpx
from companion_core.db import Database
from companion_vault.app import create_app as create_vault_app
from companion_vault.client import HttpVaultClient
from companion_vault.service import VaultService

from tests.conftest import DESK, GUEST, ROVER, VAULT_TOKEN, new_conversation, sse, text_of


def test_stated_fact_then_change_then_recall(client):
    cid = new_conversation(client)
    out = text_of(sse(client, cid, "Remember that my favourite tea is Earl Grey"))
    assert "favourite tea is Earl Grey" in out
    out = text_of(sse(client, cid, "Remember that my favourite tea is now Assam"))
    assert "Assam" in out and "replaces" in out
    events = sse(client, cid, "What is my favourite tea?")
    out = text_of(events)
    assert "Assam" in out and "Earl Grey" not in out and "[S1]" in out
    src = [d for t, d in events if t == "sources"][0]["sources"][0]
    assert src["source_type"] == "fact"
    facts = client.get("/v1/memory/facts", headers=DESK).json()
    assert [f["value"] for f in facts] == ["Assam"]
    hist = client.get(f"/v1/memory/facts/{facts[0]['id']}/history", headers=DESK).json()
    assert [h["value"] for h in hist] == ["Earl Grey", "Assam"]


def test_decision_recorded_and_recalled(client):
    cid = new_conversation(client)
    out = text_of(sse(client, cid, "Remember that we decided the rover uses a Pi 5 for the Rover project"))
    assert "Decision recorded for Rover" in out
    out = text_of(sse(client, cid, "What did we decide for the rover?"))
    assert "Pi 5" in out and "[S1]" in out
    decs = client.get("/v1/memory/decisions", headers=DESK).json()
    assert decs[0]["project_name"] == "Rover"


def test_candidates_need_confirmation_and_are_not_used(client):
    cid = new_conversation(client)
    sse(client, cid, "I live in Leeds, in case that helps.")
    cands = client.get("/v1/memory/facts/candidates", headers=DESK).json()
    assert len(cands) == 1 and cands[0]["predicate"] == "lives in" and cands[0]["status"] == "candidate"
    assert cands[0]["evidence_message_id"] and cands[0]["trust"] == "inferred"
    # not used in answers until confirmed
    assert "couldn't find" in text_of(sse(client, cid, "Where do I live?"))
    # saying it again does not create a duplicate candidate
    sse(client, cid, "As I said, I live in Leeds.")
    assert len(client.get("/v1/memory/facts/candidates", headers=DESK).json()) == 1
    client.post(f"/v1/memory/facts/{cands[0]['id']}/confirm", headers=DESK)
    assert "Leeds" in text_of(sse(client, cid, "Where do I live?"))
    assert client.get("/v1/memory/facts/candidates", headers=DESK).json() == []


def test_candidate_rejection_and_guest_isolation(client):
    cid = new_conversation(client)
    sse(client, cid, "My favourite colour is teal.")
    c = client.get("/v1/memory/facts/candidates", headers=DESK).json()[0]
    r = client.post(f"/v1/memory/facts/{c['id']}/reject", json={"reason": "no"}, headers=DESK)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    # guests cannot read or write structured memory, and their chatter never creates candidates
    gcid = new_conversation(client, GUEST)
    sse(client, gcid, "I live in Bristol.", headers=GUEST)
    assert client.get("/v1/memory/facts/candidates", headers=GUEST).status_code == 403
    assert all(c["value"] != "Bristol" for c in client.get("/v1/memory/facts/candidates", headers=DESK).json())
    # rover (shared scope only) sees no owner facts
    assert client.get("/v1/memory/facts", headers=ROVER).json() == []


def test_structured_memory_works_in_remote_mode(cfg, make_client, tmp_path):
    cfg.vault.mode = "remote"
    svc = VaultService(Database(tmp_path / "remote.db"))
    svc.migrate()
    vault_client = HttpVaultClient("http://vault.test", VAULT_TOKEN, transport=httpx.ASGITransport(app=create_vault_app(cfg, service=svc)))
    client = make_client(vault=vault_client)
    cid = new_conversation(client)
    assert "Earl Grey" in text_of(sse(client, cid, "Remember that my favourite tea is Earl Grey"))
    assert "Earl Grey" in text_of(sse(client, cid, "What's my favourite tea?"))
    sse(client, cid, "I work at Northgate Labs these days.")
    cands = client.get("/v1/memory/facts/candidates", headers=DESK).json()
    assert cands and cands[0]["value"] == "Northgate Labs"
    confirmed = client.post(f"/v1/memory/facts/{cands[0]['id']}/confirm", headers=DESK).json()
    assert confirmed["status"] == "confirmed"
    assert client.post("/v1/memory/actions", json={"title": "Order a USB speakerphone"}, headers=DESK).status_code == 201
    acts = client.get("/v1/memory/actions", headers=DESK).json()
    assert acts[0]["status"] == "draft"
    upd = client.patch(f"/v1/memory/actions/{acts[0]['id']}", json={"status": "open"}, headers=DESK).json()
    assert upd["status"] == "open"
