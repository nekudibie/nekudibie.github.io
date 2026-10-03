"""Meeting pipeline through the API with fixture STT and the explicit worker."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

import httpx
import pytest
from companion_core.clock import FakeClock
from companion_core.errors import UpstreamUnavailable
from companion_integrations.speech.base import make_wav
from companion_integrations.speech.fixture import FixtureSTT

from tests.conftest import DESK, DESK_TOKEN, GUEST, ROVER, new_conversation, sse, text_of


def chunk(text: str | None, seconds: float = 2.0) -> bytes:
    return make_wav(b"\x05\x00" * int(16000 * seconds), comment=text)


def put(client, rid: str, seq: int, data: bytes, headers=DESK, sha: str | None = "auto"):  # type: ignore[no-untyped-def]
    h = {**headers, "Content-Type": "audio/wav"}
    if sha == "auto":
        h["X-Content-SHA256"] = hashlib.sha256(data).hexdigest()
    elif sha:
        h["X-Content-SHA256"] = sha
    return client.put(f"/v1/meetings/{rid}/chunks/{seq}", content=data, headers=h)


def run_worker(client) -> int:  # type: ignore[no-untyped-def]
    st = client.app.state.companion
    return asyncio.run(st.worker.run_until_idle(max_seconds=20))


def test_recording_requires_consent_and_is_visible(client):
    r = client.post("/v1/meetings", json={"title": "Budget", "participants_informed": False}, headers=DESK)
    assert r.status_code == 422 and "knows it is being recorded" in r.text
    r = client.post("/v1/meetings", json={"title": "Budget", "participants_informed": True}, headers=DESK)
    assert r.status_code == 201 and r.json()["status"] == "recording" and r.json()["participants_informed"] is True
    rid = r.json()["id"]
    assert client.post("/v1/meetings", json={"title": "Another", "participants_informed": True}, headers=DESK).status_code == 409
    assert [m["id"] for m in client.get("/v1/meetings", headers=DESK).json()] == [rid]
    # other clients cannot touch it
    assert client.get(f"/v1/meetings/{rid}", headers=ROVER).status_code == 403
    assert client.post("/v1/meetings", json={"title": "x", "participants_informed": True}, headers=ROVER).status_code == 403
    assert client.get("/v1/jobs", headers=GUEST).status_code == 403


def test_chunk_upload_is_verified_ordered_and_idempotent(client):
    rid = client.post("/v1/meetings", json={"title": "Chunks", "participants_informed": True}, headers=DESK).json()["id"]
    c0 = chunk("hello there")
    assert put(client, rid, 0, c0).status_code == 200
    again = put(client, rid, 0, c0)
    assert again.status_code == 200 and again.json()["sha256"] == hashlib.sha256(c0).hexdigest()
    assert put(client, rid, 0, chunk("different")).status_code == 409
    assert put(client, rid, 1, chunk("x"), sha="deadbeef").status_code == 422  # corrupted/truncated upload
    assert put(client, rid, 5, chunk("x")).status_code == 409  # out of order
    assert put(client, rid, 1, b"RIFF....WAVEnotreallyaudio", sha=None).status_code == 422
    assert put(client, rid, 1, chunk("ok")).status_code == 200
    rec = client.get(f"/v1/meetings/{rid}", headers=DESK).json()
    assert rec["chunks"] == 2 and rec["recording"]["audio_ms"] == 4000
    assert client.get(f"/v1/meetings/{rid}/audio/1", headers=DESK).headers["content-type"] == "audio/wav"


def test_full_pipeline_transcript_summary_actions_and_query(client):
    rid = client.post("/v1/meetings", json={"title": "Orion budget meeting", "participants_informed": True}, headers=DESK).json()["id"]
    put(client, rid, 0, chunk("Action: Neku to send the revised budget sheet by Friday."))
    assert client.post(f"/v1/meetings/{rid}/pause", headers=DESK).json()["status"] == "paused"
    assert client.post(f"/v1/meetings/{rid}/resume", headers=DESK).json()["status"] == "recording"
    put(client, rid, 1, chunk("We decided to ship the beta in October. Can you book the test lab soon?"))
    stop = client.post(f"/v1/meetings/{rid}/stop", headers=DESK).json()
    assert stop["recording"]["status"] == "stopped" and stop["job"]["kind"] == "transcribe_recording"
    assert put(client, rid, 2, chunk("late")).status_code == 409  # no audio after stop

    assert run_worker(client) >= 2  # transcribe, then summarise
    detail = client.get(f"/v1/meetings/{rid}", headers=DESK).json()
    rec = detail["recording"]
    assert rec["status"] == "done" and rec["transcript_document_id"] and rec["summary_document_id"]
    segs = client.get(f"/v1/meetings/{rid}/segments", headers=DESK).json()
    assert [s["start_ms"] for s in segs] == [0, 2000] and all(s["speaker"] is None for s in segs)
    jobs = client.get("/v1/jobs", headers=DESK).json()
    assert {j["kind"]: j["status"] for j in jobs["jobs"]} == {"transcribe_recording": "succeeded", "summarise_recording": "succeeded"}

    actions = detail["actions"]
    by_title = {a["title"]: a for a in actions}
    budget = next(a for t, a in by_title.items() if "budget sheet" in t.lower())
    assert budget["status"] == "draft" and budget["owner"] == "Neku" and budget["due_text"] == "Friday" and budget["due_at"] and 0 < budget["due_confidence"] < 1
    lab = next(a for t, a in by_title.items() if "test lab" in t.lower())
    assert lab["owner"] is None and lab["due_at"] is None and lab["due_text"] == "soon" and lab["due_confidence"] < 0.3
    assert budget["source_quote"].startswith("Action: Neku")

    # the transcript lives in the vault with time anchors; the decision is in structured memory
    doc = client.get(f"/v1/memory/documents/{rec['transcript_document_id']}", headers=DESK).json()
    assert doc["kind"] == "meeting_transcript" and doc["provenance"]["source_ref"] == rid
    hits = client.post("/v1/memory/search", json={"query": "budget sheet", "document_ids": [rec["transcript_document_id"]]}, headers=DESK).json()["hits"]
    assert hits and hits[0]["anchor"]["kind"] == "segment" and hits[0]["anchor"]["start_time_s"] == 0.0 and hits[0]["anchor"]["segment_id"]
    decisions = client.get("/v1/memory/decisions", headers=DESK).json()
    assert any("beta in October" in d["statement"] for d in decisions)

    # ask about it in chat; the answer cites the action and keeps the uncertainty
    cid = new_conversation(client)
    events = sse(client, cid, "What was my action from the Orion budget meeting?")
    out = text_of(events)
    assert "budget sheet" in out and "owner Neku" in out and "due Friday" in out and "unconfirmed" in out and "[S" in out
    srcs = [d for t, d in events if t == "sources"][0]["sources"]
    assert any(s["source_type"] == "action" and s["anchor"] and s["anchor"]["segment_id"] for s in srcs)

    # confirming a draft creates a real obligation; the pipeline never does this by itself
    confirmed = client.post(f"/v1/meetings/{rid}/actions/{budget['id']}/confirm", json={"due_at": "2026-10-09"}, headers=DESK).json()
    assert confirmed["status"] == "open" and confirmed["due_confidence"] == 1.0


class FlakyOnce(FixtureSTT):
    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, wav_bytes, *, language=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls == 2:
            raise UpstreamUnavailable("stt host went away")
        return await super().transcribe(wav_bytes, language=language)


def test_interrupted_transcription_resumes_without_duplicates(cfg, make_client):
    clock = FakeClock(datetime(2026, 10, 3, 10, 0, tzinfo=UTC))
    stt = FlakyOnce()
    client = make_client(stt=stt, clock=clock)
    rid = client.post("/v1/meetings", json={"title": "Flaky", "participants_informed": True}, headers=DESK).json()["id"]
    for i, text in enumerate(["first part", "second part", "third part"]):
        put(client, rid, i, chunk(text))
    client.post(f"/v1/meetings/{rid}/stop", headers=DESK)
    run_worker(client)
    job = client.get("/v1/jobs", headers=DESK).json()["jobs"][0]
    assert job["kind"] == "transcribe_recording" and job["status"] == "queued" and job["attempts"] == 1  # retry scheduled
    assert client.get(f"/v1/meetings/{rid}", headers=DESK).json()["recording"]["transcribed_through"] == 0
    clock.advance(seconds=120)  # past the backoff
    run_worker(client)
    segs = client.get(f"/v1/meetings/{rid}/segments", headers=DESK).json()
    assert [s["text"] for s in segs] == ["first part", "second part", "third part"]
    assert stt.calls == 4  # chunk 0, failed chunk 1, then chunks 1 and 2 only (no re-run of chunk 0)
    assert client.get(f"/v1/meetings/{rid}", headers=DESK).json()["recording"]["status"] == "done"


def test_ambiguous_meeting_name_is_reported(client):
    st = client.app.state.companion
    for _ in range(2):
        rid = client.post("/v1/meetings", json={"title": "Planning", "participants_informed": True}, headers=DESK).json()["id"]
        put(client, rid, 0, chunk("Action: Priya to write the plan by Monday."))
        client.post(f"/v1/meetings/{rid}/stop", headers=DESK)
        st.recordings.set_status(rid, "done")
    cid = new_conversation(client)
    out = text_of(sse(client, cid, "What were my actions from the planning meeting?"))
    assert "more than one meeting" in out and out.count("Planning") == 2 and "Which one" in out
    out = text_of(sse(client, cid, "What were my actions from the Hydra meeting?"))
    assert "no recorded meetings" in out.lower() or "no meeting" in out.lower()


def test_router_phrases_for_recording(client):
    cid = new_conversation(client)
    events = sse(client, cid, "start recording this meeting")
    ui = [d for t, d in events if t == "ui"][0]
    assert ui["action"] == "open_panel" and ui["payload"]["requires_consent"] is True
    assert client.get("/v1/meetings", headers=DESK).json() == []  # nothing started by voice alone
    assert "no recording in progress" in text_of(sse(client, cid, "stop recording"))
    rid = client.post("/v1/meetings", json={"title": "Voice", "participants_informed": True}, headers=DESK).json()["id"]
    events = sse(client, cid, "pause recording")
    assert client.get(f"/v1/meetings/{rid}", headers=DESK).json()["recording"]["status"] == "paused"
    assert [d for t, d in events if t == "ui"][0]["payload"]["paused"] is True
    events = sse(client, cid, "stop recording")
    assert "transcription queued" in text_of(events)
    assert client.get("/v1/jobs", headers=DESK).json()["jobs"][0]["kind"] == "transcribe_recording"


def test_model_cannot_start_recording_without_confirmation(make_client):
    from companion_integrations.llm.fixture import ScriptedProvider

    llm = ScriptedProvider([[{"name": "meeting_start", "arguments": {"title": "Sneaky", "participants_informed": True}}], ["I need you to confirm on screen."]])
    client = make_client(llm=llm)
    cid = new_conversation(client)
    events = sse(client, cid, "record this")
    call = [d for t, d in events if t == "tool_call"][0]
    assert call["status"] == "needs_confirmation"
    assert client.get("/v1/meetings", headers=DESK).json() == []


def test_cancel_and_delete(client):
    rid = client.post("/v1/meetings", json={"title": "Bin", "participants_informed": True}, headers=DESK).json()["id"]
    put(client, rid, 0, chunk("something"))
    client.post(f"/v1/meetings/{rid}/stop", headers=DESK)
    assert client.post(f"/v1/meetings/{rid}/cancel", headers=DESK).json()["status"] == "cancelled"
    assert client.get("/v1/jobs", headers=DESK).json()["jobs"][0]["status"] == "cancelled"
    rec_dir = client.app.state.companion.recordings.get(rid).dir
    out = client.delete(f"/v1/meetings/{rid}", headers=DESK).json()
    assert out["deleted"] is True
    import os

    assert not os.path.exists(rec_dir)
    assert client.get(f"/v1/meetings/{rid}", headers=DESK).status_code == 404


@pytest.mark.asyncio
async def test_desk_client_records_meeting_in_chunks(cfg, tmp_path):
    from companion_api.app import create_app
    from companion_audio.backends import FileCapture
    from companion_audio.meeting import MeetingUploader
    from starlette.testclient import TestClient

    app = create_app(cfg)
    tc = TestClient(app)
    tc.__enter__()
    try:
        wav = tmp_path / "m.wav"
        wav.write_bytes(make_wav(b"\x01\x00" * (16000 * 5), comment="five seconds of meeting"))
        up = MeetingUploader("http://api.test", DESK_TOKEN, FileCapture(wav), chunk_seconds=2.0, transport=httpx.ASGITransport(app=app))
        with pytest.raises(ValueError):
            await up.start("No consent", participants_informed=False)
        rid = await up.start("Desk meeting", participants_informed=True)
        stats = await up.run()
        await up.aclose()
        assert stats.chunks_sent == 3 and stats.retries == 0  # 2 s + 2 s + 1 s
        rec = tc.get(f"/v1/meetings/{rid}", headers=DESK).json()["recording"]
        assert rec["status"] == "stopped" and rec["chunk_count"] == 3 and rec["audio_ms"] == 5000
    finally:
        tc.__exit__(None, None, None)
