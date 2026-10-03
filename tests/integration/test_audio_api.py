from __future__ import annotations

import json

from companion_integrations.speech.base import inspect_wav, make_wav

from tests.conftest import DESK, GUEST, new_conversation


def _wav(text: str | None, seconds: float = 1.0) -> bytes:
    return make_wav(b"\x00\x00" * int(16000 * seconds), comment=text)


def _sse(client, path, body, headers):  # type: ignore[no-untyped-def]
    events = []
    with client.stream("POST", path, content=body, headers={**headers, "Content-Type": "audio/wav"}) as r:
        assert r.status_code == 200, r.read()
        et = "message"
        for line in r.iter_lines():
            if line.startswith("event:"):
                et = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((et, json.loads(line.split(":", 1)[1])))
    return events


def test_transcribe_and_speak_with_fixtures(client):
    r = client.post("/v1/audio/transcribe", content=_wav("what time is it"), headers={**DESK, "Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json()["text"] == "what time is it" and r.json()["is_fixture"] is True
    r = client.post("/v1/audio/speak", json={"text": "The desk lamp is on."}, headers=DESK)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.headers["x-companion-fixture"] == "true"
    info = inspect_wav(r.content)
    assert info.sample_rate == 22050 and 0.5 < info.duration_s < 5
    st = client.get("/v1/audio/status", headers=DESK).json()
    assert st["stt"]["is_fixture"] and st["tts"]["is_fixture"] and st["wake_word"]["enabled"] is False


def test_audio_permissions_and_validation(client):
    assert client.post("/v1/audio/transcribe", content=_wav("x"), headers={**GUEST, "Content-Type": "audio/wav"}).status_code == 403
    assert client.post("/v1/audio/speak", json={"text": "hi"}, headers=GUEST).status_code == 403
    assert client.post("/v1/audio/transcribe", content=_wav("x"), headers=DESK).status_code == 422  # missing content type
    assert client.post("/v1/audio/transcribe", content=b"not audio at all....................................", headers={**DESK, "Content-Type": "audio/wav"}).status_code == 422
    assert client.post("/v1/audio/speak", json={"text": ""}, headers=DESK).status_code == 422


def test_voice_turn_streams_transcript_then_turn(client):
    cid = new_conversation(client)
    events = _sse(client, f"/v1/conversations/{cid}/voice", _wav("turn on the desk lamp"), DESK)
    types = [t for t, _ in events]
    assert types[0] == "state" and events[0][1]["state"] == "transcribing"
    tr = [d for t, d in events if t == "transcript"][0]
    assert tr["text"] == "turn on the desk lamp" and tr["is_fixture"] is True
    assert "Desk lamp turned on" in "".join(d["text"] for t, d in events if t == "token")
    assert [d for t, d in events if t == "done"][0]["route"] == "deterministic"
    msgs = client.get(f"/v1/conversations/{cid}", headers=DESK).json()["messages"]
    assert msgs[0]["meta"]["input_mode"] == "voice"


def test_voice_turn_with_no_speech_is_honest(client):
    cid = new_conversation(client)
    events = _sse(client, f"/v1/conversations/{cid}/voice", _wav(None), DESK)
    err = [d for t, d in events if t == "error"][0]
    assert err["code"] == "no_speech" and [d for t, d in events if t == "state"][-1]["state"] == "idle"
    assert client.get(f"/v1/conversations/{cid}", headers=DESK).json()["messages"] == []


def test_voice_turn_rejects_other_clients_conversation(client):
    from tests.conftest import ROVER

    cid = new_conversation(client)
    r = client.post(f"/v1/conversations/{cid}/voice", content=_wav("hello"), headers={**ROVER, "Content-Type": "audio/wav"})
    assert r.status_code == 403
