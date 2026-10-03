"""Fixture speech providers for development and tests. Always labelled as fixtures.

FixtureSTT returns the text carried in the WAV's INFO/ICMT comment (tests put the
"spoken" words there); with no comment it returns an empty transcript rather than
inventing speech. FixtureTTS produces a quiet tone whose length scales with the text.
"""

from __future__ import annotations

import math
import struct
import time
from collections.abc import AsyncIterator

from companion_contracts.health import DependencyStatus
from companion_core.errors import ValidationFailed

from .base import AudioClip, Transcript, TranscriptSegment, inspect_wav


class FixtureSTT:
    name = "fixture"
    model = "fixture-stt"
    is_fixture = True

    async def transcribe(self, wav_bytes: bytes, *, language: str | None = None) -> Transcript:
        started = time.monotonic()
        try:
            info = inspect_wav(wav_bytes)
        except Exception as exc:  # noqa: BLE001
            raise ValidationFailed(f"not a valid WAV file: {exc}") from exc
        text = (info.comment or "").strip()
        segs = [TranscriptSegment(id=0, start_s=0.0, end_s=info.duration_s, text=text, confidence=None)] if text else []
        return Transcript(
            text=text, language=language or "en", duration_s=info.duration_s, segments=segs, provider=self.name, model=self.model,
            is_fixture=True, processing_ms=int((time.monotonic() - started) * 1000),
        )

    async def health(self) -> DependencyStatus:
        return DependencyStatus(name="stt", status="fixture", detail="fixture STT: reads text from the WAV comment, never real recognition")


class FixtureTTS:
    name = "fixture"
    voice = "fixture-tone"
    is_fixture = True
    sample_rate = 22050

    async def synthesize(self, text: str) -> AudioClip:
        words = max(1, len(text.split()))
        seconds = min(20.0, 0.25 * words)
        n = int(self.sample_rate * seconds)
        pcm = bytearray()
        for i in range(n):
            env = min(1.0, i / 400, (n - i) / 400)
            pcm += struct.pack("<h", int(2500 * env * math.sin(2 * math.pi * 440 * i / self.sample_rate)))
        return AudioClip(sample_rate=self.sample_rate, channels=1, sample_width=2, pcm=bytes(pcm), provider=self.name, voice=self.voice, is_fixture=True)

    async def stream(self, text: str) -> AsyncIterator[AudioClip]:
        for sentence in [s for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()]:
            yield await self.synthesize(sentence)

    async def health(self) -> DependencyStatus:
        return DependencyStatus(name="tts", status="fixture", detail="fixture TTS: a tone, not speech")
