from __future__ import annotations

from tests.conftest import DESK, new_conversation, sse, text_of


def test_remember_then_recall_with_citation(client):
    cid = new_conversation(client)
    events = sse(client, cid, "Remember that we decided to use SQLite FTS5 for the Lantern project before any vector database.")
    assert [d["name"] for t, d in events if t == "tool_call"] == ["decision_record"]
    saved = [d for t, d in events if t == "tool_result"][0]
    assert saved["ok"] and saved["data"]["kind"] == "decision" and saved["data"]["decision_id"]
    events = sse(client, cid, "What did we decide about the Lantern project?")
    out = text_of(events)
    assert "[S1]" in out and "FTS5" in out
    srcs = [d for t, d in events if t == "sources"][0]["sources"]
    assert srcs[0]["document_id"] == saved["data"]["document_id"] and srcs[0]["anchor"]["kind"] == "offset"
    done = [d for t, d in events if t == "done"][0]
    assert done["route"] == "fixture_llm"
    stored = client.get(f"/v1/conversations/{cid}", headers=DESK).json()["messages"]
    assert stored[-1]["role"] == "assistant" and stored[-1]["sources"][0]["label"] == "S1"


def test_missing_evidence_gives_honest_answer(client):
    cid = new_conversation(client)
    out = text_of(sse(client, cid, "What did we decide about the Orion launch?"))
    assert "couldn't find" in out and "won't guess" in out


def test_contradiction_resolved_by_correction(client):
    d1 = client.post("/v1/memory/notes", json={"text": "Decision: study lamp colour temperature is 2700K.", "kind": "decision"}, headers=DESK).json()
    d2 = client.post(f"/v1/memory/documents/{d1['id']}/correct", json={"new_text": "Decision: study lamp colour temperature is 4000K (changed from 2700K).", "reason": "that's changed"}, headers=DESK).json()
    assert d2["revision"] == 2 and d2["supersedes_id"] == d1["id"]
    hits = client.post("/v1/memory/search", json={"query": "study lamp colour temperature"}, headers=DESK).json()["hits"]
    assert len(hits) == 1 and hits[0]["document_id"] == d2["id"] and "4000K" in hits[0]["text"]
    hist = client.get(f"/v1/memory/documents/{d1['id']}/history", headers=DESK).json()
    assert [h["revision"] for h in hist] == [1, 2]
    cid = new_conversation(client)
    assert "4000K" in text_of(sse(client, cid, "What colour temperature did we decide for the study lamp?"))


def test_delete_removes_from_retrieval(client):
    d = client.post("/v1/memory/notes", json={"text": "Gift idea: telescope for Sam."}, headers=DESK).json()
    r = client.delete(f"/v1/memory/documents/{d['id']}", headers=DESK, params={"reason": "no longer needed"})
    assert r.status_code == 200 and r.json()["chunks_removed"] == 1
    assert client.post("/v1/memory/search", json={"query": "telescope gift"}, headers=DESK).json()["hits"] == []
    assert client.get(f"/v1/memory/documents/{d['id']}", headers=DESK).json()["deleted_at"]


def test_conversation_history_and_listing(client):
    cid = new_conversation(client)
    sse(client, cid, "what time is it?")
    convs = client.get("/v1/conversations", headers=DESK).json()
    assert convs[0]["id"] == cid and convs[0]["message_count"] == 2 and convs[0]["title"] == "what time is it?"
    assert client.get("/v1/conversations/conv_nope", headers=DESK).status_code == 404


def test_message_validation(client):
    cid = new_conversation(client)
    assert client.post(f"/v1/conversations/{cid}/messages", json={"content": ""}, headers=DESK).status_code == 422
    assert client.post(f"/v1/conversations/{cid}/messages", json={"content": "x", "extra": 1}, headers=DESK).status_code == 422


def test_export_and_stats(client):
    client.post("/v1/memory/notes", json={"text": "exportable note"}, headers=DESK)
    r = client.get("/v1/memory/export", headers=DESK)
    assert r.status_code == 200 and "exportable note" in r.text
    assert client.get("/v1/memory/stats", headers=DESK).json()["documents"] >= 1
