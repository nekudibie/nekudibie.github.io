"""Desk-side meeting recording: capture in chunks, upload each with a checksum, stop explicitly.

Each chunk is a complete WAV sent with ``X-Content-SHA256``; a failed upload is retried
with the same sequence number (the server de-duplicates by content), so a flaky network
cannot duplicate or silently drop audio.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from dataclasses import dataclass, field

import httpx
from companion_core.logging import get_logger
from companion_integrations.speech.base import make_wav

from .backends import RATE, CaptureBackend

log = get_logger(__name__)


@dataclass
class UploadStats:
    recording_id: str = ""
    chunks_sent: int = 0
    bytes_sent: int = 0
    retries: int = 0
    errors: list[str] = field(default_factory=list)


class MeetingUploader:
    def __init__(self, api_url: str, token: str, capture: CaptureBackend, *, chunk_seconds: float = 20.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.capture = capture
        self.chunk_seconds = chunk_seconds
        self._http = httpx.AsyncClient(base_url=api_url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=httpx.Timeout(connect=3.0, read=60.0, write=120.0, pool=3.0), transport=transport)
        self._stop = threading.Event()
        self.stats = UploadStats()

    async def start(self, title: str, *, participants_informed: bool, route: str = "personal") -> str:
        if not participants_informed:
            raise ValueError("refusing to record: participants_informed must be true")
        r = await self._http.post("/v1/meetings", json={"title": title, "participants_informed": True, "route": route})
        r.raise_for_status()
        self.stats.recording_id = r.json()["id"]
        return self.stats.recording_id

    def request_stop(self) -> None:
        self._stop.set()

    def _capture_chunk(self) -> bytes | None:
        """Read up to chunk_seconds of PCM, or until stop; None when the source is exhausted."""
        target = int(RATE * 2 * self.chunk_seconds)
        buf = bytearray()
        while len(buf) < target and not self._stop.is_set():
            piece = self.capture.read()
            if piece is None:
                break
            buf += piece
        if not buf:
            return None
        return bytes(buf)

    async def _upload(self, seq: int, wav: bytes) -> None:
        digest = hashlib.sha256(wav).hexdigest()
        delay = 0.5
        for attempt in range(5):
            try:
                r = await self._http.put(f"/v1/meetings/{self.stats.recording_id}/chunks/{seq}", content=wav, headers={"Content-Type": "audio/wav", "X-Content-SHA256": digest})
                if r.status_code == 200:
                    self.stats.chunks_sent += 1
                    self.stats.bytes_sent += len(wav)
                    return
                if r.status_code in {409, 422}:
                    raise RuntimeError(f"chunk {seq} rejected: {r.text[:200]}")
            except httpx.TransportError as exc:
                self.stats.errors.append(f"{exc.__class__.__name__}")
            if attempt == 4:
                raise RuntimeError(f"chunk {seq} could not be uploaded after retries")
            self.stats.retries += 1
            await asyncio.sleep(delay)
            delay *= 2

    async def run(self) -> UploadStats:
        """Capture and upload until stop is requested or the source ends; then stop the recording."""
        self.capture.start()
        seq = 0
        try:
            while True:
                pcm = await asyncio.to_thread(self._capture_chunk)
                if pcm is None:
                    break
                await self._upload(seq, make_wav(pcm, sample_rate=RATE, comment=getattr(self.capture, "comment", None)))
                seq += 1
                if self._stop.is_set():
                    break
        finally:
            self.capture.stop()
        r = await self._http.post(f"/v1/meetings/{self.stats.recording_id}/stop")
        r.raise_for_status()
        return self.stats

    async def aclose(self) -> None:
        await self._http.aclose()
