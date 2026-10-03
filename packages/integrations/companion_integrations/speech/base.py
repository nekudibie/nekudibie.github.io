from __future__ import annotations

import io
import struct
import wave
from collections.abc import AsyncIterator
from typing import Protocol

from companion_contracts.health import DependencyStatus
from pydantic import BaseModel, ConfigDict, Field


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    start_s: float
    end_s: float
    text: str
    confidence: float | None = None


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    language: str | None = None
    duration_s: float
    segments: list[TranscriptSegment] = Field(default_factory=list)
    provider: str
    model: str
    is_fixture: bool = False
    processing_ms: int = 0


class AudioClip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_rate: int
    channels: int
    sample_width: int  # bytes per sample
    pcm: bytes
    provider: str
    voice: str
    is_fixture: bool = False

    @property
    def duration_s(self) -> float:
        frames = len(self.pcm) / max(1, self.channels * self.sample_width)
        return frames / self.sample_rate

    def to_wav(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(self.sample_width)
            w.setframerate(self.sample_rate)
            w.writeframes(self.pcm)
        return buf.getvalue()


class STTProvider(Protocol):
    name: str
    model: str
    is_fixture: bool

    async def transcribe(self, wav_bytes: bytes, *, language: str | None = None) -> Transcript: ...
    async def health(self) -> DependencyStatus: ...


class TTSProvider(Protocol):
    name: str
    voice: str
    is_fixture: bool

    async def synthesize(self, text: str) -> AudioClip: ...
    def stream(self, text: str) -> AsyncIterator[AudioClip]: ...
    async def health(self) -> DependencyStatus: ...


class WavInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_rate: int
    channels: int
    sample_width: int
    frames: int
    duration_s: float
    comment: str | None = None


def inspect_wav(data: bytes) -> WavInfo:
    """Validate a WAV container and read its parameters (and an INFO/ICMT comment if any)."""
    with wave.open(io.BytesIO(data), "rb") as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    return WavInfo(sample_rate=sr, channels=ch, sample_width=sw, frames=n, duration_s=n / sr if sr else 0.0, comment=_read_icmt(data))


def make_wav(pcm: bytes, *, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2, comment: str | None = None) -> bytes:
    """Build a WAV file; an optional INFO/ICMT chunk carries a comment (used by the fixture STT)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    data = bytearray(buf.getvalue())
    if comment:
        text = comment.encode("utf-8") + b"\x00"
        if len(text) % 2:
            text += b"\x00"
        icmt = b"ICMT" + struct.pack("<I", len(text)) + text
        info = b"LIST" + struct.pack("<I", 4 + len(icmt)) + b"INFO" + icmt
        data += info
        struct.pack_into("<I", data, 4, len(data) - 8)
    return bytes(data)


def _read_icmt(data: bytes) -> str | None:
    pos = 12
    while pos + 8 <= len(data):
        cid = data[pos : pos + 4]
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        if cid == b"LIST" and data[pos + 8 : pos + 12] == b"INFO":
            sub = pos + 12
            end = pos + 8 + size
            while sub + 8 <= end:
                sid = data[sub : sub + 4]
                ssize = struct.unpack("<I", data[sub + 4 : sub + 8])[0]
                if sid == b"ICMT":
                    return data[sub + 8 : sub + 8 + ssize].rstrip(b"\x00").decode("utf-8", "replace")
                sub += 8 + ssize + (ssize % 2)
        pos += 8 + size + (size % 2)
    return None
