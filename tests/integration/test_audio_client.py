"""The native audio client against the real API (in-process) with fixture STT/TTS."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from companion_api.app import create_app
from companion_audio.backends import FileCapture, NullPlayback
from companion_audio.client import AudioClient, ClientConfig
from companion_audio.wakeword import ScriptedDetector
from companion_integrations.speech.base import make_wav

from tests.conftest import DESK_TOKEN


@pytest.fixture
def api_transport(cfg):
    """In-process API with its lifespan running (TestClient) exposed as an ASGI transport."""
    from starlette.testclient import TestClient

    app = create_app(cfg)
    tc = TestClient(app)
    tc.__enter__()
    yield httpx.ASGITransport(app=app)
    tc.__exit__(None, None, None)


def _utterance(tmp_path, text: str, seconds: float = 1.2):
    p = tmp_path / "utt.wav"
    p.write_bytes(make_wav(b"\x10\x00" * int(16000 * seconds), comment=text))
    return p


@pytest.mark.asyncio
async def test_ptt_turn_hears_speaks_and_reports_states(cfg, api_transport, tmp_path):
    states: list[str] = []
    playback = NullPlayback()
    client = AudioClient(ClientConfig("http://api.test", DESK_TOKEN), FileCapture(_utterance(tmp_path, "turn on the desk lamp")), playback,
                         transport=api_transport, on_state=lambda s, d: states.append(s))
    client.press_ptt()
    client.release_ptt()
    res = await client.ptt_turn()
    assert res.transcript == "turn on the desk lamp" and res.is_fixture_stt
    assert "Desk lamp turned on" in res.reply and res.route == "deterministic" and res.error is None
    assert states[:3] == ["listening", "transcribing", "thinking"] and "speaking" in states and states[-1] == "idle"
    assert len(playback.played) == 1 and playback.played[0][:4] == b"RIFF"
    await client.aclose()


@pytest.mark.asyncio
async def test_barge_in_stops_playback(cfg, api_transport, tmp_path):
    playback = NullPlayback(simulate_duration=True)
    client = AudioClient(ClientConfig("http://api.test", DESK_TOKEN), FileCapture(_utterance(tmp_path, "tell me about otters and badgers and foxes in great detail please")), playback, transport=api_transport)
    client.press_ptt()
    client.release_ptt()

    async def interrupt():
        for _ in range(300):
            if client.state == "speaking":
                client.press_ptt()  # barge-in
                return
            await asyncio.sleep(0.01)

    res, _ = await asyncio.gather(client.ptt_turn(), interrupt())
    assert res.reply and playback.stopped >= 1 and client.state == "idle" and client.detail == "interrupted"
    await client.aclose()


@pytest.mark.asyncio
async def test_mute_blocks_capture_and_is_labelled_software(cfg, api_transport, tmp_path):
    client = AudioClient(ClientConfig("http://api.test", DESK_TOKEN), FileCapture(_utterance(tmp_path, "what time is it")), NullPlayback(), transport=api_transport)
    assert client.toggle_mute() is True and client.state == "muted" and "software" in client.detail
    res = await client.ptt_turn()
    assert res.error == "muted" and res.transcript == ""
    await client.aclose()


@pytest.mark.asyncio
async def test_wake_word_loop_takes_one_turn(cfg, api_transport, tmp_path):
    utt = _utterance(tmp_path, "what time is it", seconds=2.0)
    cfg_c = ClientConfig("http://api.test", DESK_TOKEN, wake_word=ScriptedDetector(trigger_after_chunks=3), wake_threshold=0.5, silence_ms=200, silence_rms=100000)
    client = AudioClient(cfg_c, FileCapture(utt), NullPlayback(), transport=api_transport)
    turns = await client.wake_loop(max_turns=1)
    assert turns == 1 and client.last is not None and "It's" in client.last.reply
    await client.aclose()


@pytest.mark.asyncio
async def test_offline_api_is_reported_not_crashed(tmp_path):
    def down(request):
        raise httpx.ConnectError("no route")

    client = AudioClient(ClientConfig("http://api.test", DESK_TOKEN), FileCapture(_utterance(tmp_path, "hello")), NullPlayback(), transport=httpx.MockTransport(down))
    client.press_ptt()
    client.release_ptt()
    res = await client.ptt_turn()
    assert res.error and "unreachable" in res.error and client.state == "offline"
    await client.aclose()


def test_too_short_utterance_is_ignored(tmp_path):
    client = AudioClient(ClientConfig("http://api.test", DESK_TOKEN), FileCapture(_utterance(tmp_path, "x", seconds=0.05)), NullPlayback())
    res = asyncio.run(client.send_utterance(b"\x00\x00" * 100))
    assert res.error == "too short" and time.monotonic() > 0
