"""The native voice client: push-to-talk, barge-in, honest state reporting.

State machine: idle -> listening (PTT held or wake word) -> transcribing/thinking (server
turn) -> speaking (TTS playback) -> idle. Pressing PTT while speaking stops playback first
(barge-in). A software mute blocks capture here but is *not* a hardware disconnect; the
indicator says "muted (software)" for that reason.
"""

from __future__ import annotations

import array
import asyncio
import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from companion_core.logging import get_logger
from companion_integrations.speech.base import make_wav

from .backends import CHUNK_FRAMES, RATE, CaptureBackend, PlaybackBackend
from .wakeword import WakeWordDetector

log = get_logger(__name__)

STATES = ("idle", "listening", "transcribing", "thinking", "speaking", "muted", "offline", "error")


def rms16(chunk: bytes) -> int:
    """RMS of little-endian 16-bit PCM (pure Python; ``audioop`` was removed in Python 3.13)."""
    if len(chunk) < 2:
        return 0
    samples = array.array("h")
    samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
    if sys_byteorder_big:
        samples.byteswap()
    return int(math.sqrt(sum(x * x for x in samples) / len(samples)))


import sys as _sys  # noqa: E402

sys_byteorder_big = _sys.byteorder == "big"


@dataclass
class ClientConfig:
    api_url: str
    token: str
    conversation_id: str | None = None
    max_utterance_s: float = 30.0
    silence_rms: int = 400
    silence_ms: int = 900
    wake_word: WakeWordDetector | None = None
    wake_threshold: float = 0.6
    speak_replies: bool = True
    language: str | None = None


@dataclass
class TurnResult:
    transcript: str = ""
    reply: str = ""
    route: str | None = None
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    is_fixture_stt: bool = False


class AudioClient:
    def __init__(self, cfg: ClientConfig, capture: CaptureBackend, playback: PlaybackBackend, *, transport: httpx.AsyncBaseTransport | None = None, on_state: Callable[[str, str], None] | None = None) -> None:
        self.cfg = cfg
        self.capture = capture
        self.playback = playback
        self.on_state = on_state or (lambda s, d: None)
        self.state = "idle"
        self.detail = ""
        self.software_muted = False
        self._http = httpx.AsyncClient(base_url=cfg.api_url.rstrip("/"), headers={"Authorization": f"Bearer {cfg.token}"}, timeout=httpx.Timeout(connect=3.0, read=120.0, write=30.0, pool=3.0), transport=transport)
        self._ptt = threading.Event()
        self._stop_speaking = threading.Event()
        self.last: TurnResult | None = None
        self._announced: set[str] = set()

    # -- state ---------------------------------------------------------
    def _set(self, state: str, detail: str = "") -> None:
        assert state in STATES
        self.state, self.detail = state, detail
        self.on_state(state, detail)

    def press_ptt(self) -> None:
        """Barge-in: stop any speech, then start listening."""
        if self.state == "speaking" or self.playback.is_playing():
            self._stop_speaking.set()
            self.playback.stop()
        self._ptt.set()

    def release_ptt(self) -> None:
        self._ptt.clear()

    def stop_speaking(self) -> None:
        self._stop_speaking.set()
        self.playback.stop()

    def toggle_mute(self) -> bool:
        self.software_muted = not self.software_muted
        self._set("muted" if self.software_muted else "idle", "software mute, not a hardware cut" if self.software_muted else "")
        return self.software_muted

    # -- capture -------------------------------------------------------
    def _record_until_release(self) -> bytes:
        """Hold-to-talk: record while PTT is held, or until silence/max length when wake-triggered."""
        self.capture.start()
        buf = bytearray()
        started = time.monotonic()
        quiet_ms = 0
        try:
            while True:
                chunk = self.capture.read()
                if chunk is None:
                    if self._ptt.is_set() and time.monotonic() - started < self.cfg.max_utterance_s:
                        time.sleep(0.01)
                        continue
                    break
                buf += chunk
                if not self._ptt.is_set():
                    rms = rms16(chunk)
                    quiet_ms = quiet_ms + int(1000 * len(chunk) / 2 / RATE) if rms < self.cfg.silence_rms else 0
                    if quiet_ms >= self.cfg.silence_ms and len(buf) > RATE * 2 * 0.5:
                        break
                if time.monotonic() - started >= self.cfg.max_utterance_s:
                    break
        finally:
            self.capture.stop()
        return bytes(buf)

    # -- turn ----------------------------------------------------------
    async def ensure_conversation(self) -> str:
        if self.cfg.conversation_id:
            return self.cfg.conversation_id
        r = await self._http.post("/v1/conversations", json={})
        r.raise_for_status()
        self.cfg.conversation_id = r.json()["id"]
        return self.cfg.conversation_id

    async def send_utterance(self, pcm: bytes, *, comment: str | None = None) -> TurnResult:
        result = TurnResult()
        if len(pcm) < RATE * 2 * 0.2:
            result.error = "too short"
            self._set("idle")
            return result
        wav = make_wav(pcm, sample_rate=RATE, comment=comment)
        try:
            cid = await self.ensure_conversation()
            self._set("transcribing")
            params = {"language": self.cfg.language} if self.cfg.language else None
            async with self._http.stream("POST", f"/v1/conversations/{cid}/voice", content=wav, headers={"Content-Type": "audio/wav"}, params=params) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    result.error = f"api {resp.status_code}: {body[:200]!r}"
                    self._set("error", result.error)
                    return result
                et = "message"
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        et = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data = json.loads(line.split(":", 1)[1])
                        result.events.append({"type": et, **data})
                        if et == "transcript":
                            result.transcript = data["text"]
                            result.is_fixture_stt = data.get("is_fixture", False)
                            self._set("thinking", f"heard: {data['text'][:60]}")
                        elif et == "token":
                            result.reply += data["text"]
                        elif et == "state" and data["state"] in {"thinking", "tool_running"}:
                            self._set("thinking", data.get("detail") or "")
                        elif et == "error":
                            result.error = data["message"]
                        elif et == "done":
                            result.route = data["route"]
        except httpx.TransportError as exc:
            result.error = f"api unreachable ({exc.__class__.__name__})"
            self._set("offline", result.error)
            return result
        self.last = result
        if result.reply and self.cfg.speak_replies and not result.error:
            await self.speak(result.reply)
        else:
            self._set("idle")
        return result

    async def speak(self, text: str) -> bool:
        """Fetch TTS and play it; returns False when interrupted."""
        self._stop_speaking.clear()
        try:
            r = await self._http.post("/v1/audio/speak", json={"text": text[:2000]})
        except httpx.TransportError as exc:
            self._set("offline", f"tts unreachable ({exc.__class__.__name__})")
            return False
        if r.status_code != 200:
            self._set("idle", f"tts unavailable ({r.status_code})")
            return False
        self._set("speaking", "fixture tone" if r.headers.get("x-companion-fixture") == "true" else r.headers.get("x-companion-voice", ""))
        if self._stop_speaking.is_set():  # interrupted between fetching and starting playback
            self._set("idle", "interrupted")
            return False
        self.playback.play(r.content)
        while self.playback.is_playing() and not self._stop_speaking.is_set():
            await asyncio.sleep(0.02)
        if self._stop_speaking.is_set():
            self.playback.stop()
            self._set("idle", "interrupted")
            return False
        self._set("idle")
        return True

    # -- loops ---------------------------------------------------------
    async def ptt_turn(self) -> TurnResult:
        """Record while PTT is held (the caller sets/clears it), then run the turn."""
        if self.software_muted:
            self._set("muted", "software mute, not a hardware cut")
            return TurnResult(error="muted")
        self._set("listening", "push-to-talk")
        pcm = await asyncio.to_thread(self._record_until_release)
        comment = getattr(self.capture, "comment", None)
        return await self.send_utterance(pcm, comment=comment)

    async def wake_loop(self, *, max_turns: int | None = None) -> int:
        """Listen continuously for the wake word (ring buffer only), then take one utterance."""
        det = self.cfg.wake_word
        if det is None:
            raise RuntimeError("no wake-word detector configured")
        turns = 0
        self.capture.start()
        try:
            while max_turns is None or turns < max_turns:
                if self.software_muted:
                    await asyncio.sleep(0.1)
                    continue
                chunk = await asyncio.to_thread(self.capture.read)
                if chunk is None:
                    break
                if det.feed(chunk) >= self.cfg.wake_threshold:
                    det.reset()
                    self.capture.stop()
                    self._set("listening", f"wake word ({det.name})")
                    pcm = await asyncio.to_thread(self._record_until_release)
                    await self.send_utterance(pcm, comment=getattr(self.capture, "comment", None))
                    turns += 1
                    if max_turns is None or turns < max_turns:
                        self.capture.start()
        finally:
            self.capture.stop()
        return turns

    async def announce_reminders(self) -> int:
        """Speak delivered-but-unacknowledged reminders (polled while idle); acknowledgement stays on screen or by voice."""
        if self.state not in {"idle"} or self.software_muted:
            return 0
        try:
            r = await self._http.get("/v1/reminders/pending")
        except httpx.TransportError:
            return 0
        if r.status_code != 200:
            return 0
        spoken = 0
        for rem in r.json():
            key = f"{rem['id']}:{rem.get('delivery_count', 1)}"
            if key in self._announced:
                continue
            self._announced.add(key)
            await self.speak(f"Reminder: {rem['title']}." + (f" {rem['body']}" if rem.get("body") else ""))
            spoken += 1
        return spoken

    async def aclose(self) -> None:
        await self._http.aclose()


__all__ = ["AudioClient", "ClientConfig", "TurnResult", "STATES", "CHUNK_FRAMES"]
