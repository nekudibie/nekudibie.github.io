"""Piper TTS adapter. Optional dependency: ``companion-integrations[tts]`` (GPL-3.0 component).

Verified API (docs/SOURCES.md): ``PiperVoice.load(path.onnx)``; ``voice.synthesize(text, syn_config)``
yields ``AudioChunk`` objects with ``sample_rate``, ``sample_width``, ``sample_channels`` and
``audio_int16_bytes``; ``SynthesisConfig(length_scale=...)``. Voices are downloaded with
``python3 -m piper.download_voices <name>`` into ``voices_dir`` (they are not bundled).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from companion_contracts.health import DependencyStatus
from companion_core.errors import NotConfigured, UpstreamError

from .base import AudioClip


class PiperTTS:
    name = "piper"
    is_fixture = False

    def __init__(self, voice: str, voices_dir: Path, *, length_scale: float = 1.0) -> None:
        self.voice = voice
        self.voices_dir = voices_dir
        self.length_scale = length_scale
        self._voice: Any = None
        self._lock = asyncio.Lock()

    @property
    def voice_path(self) -> Path:
        return self.voices_dir / f"{self.voice}.onnx"

    def _load(self) -> Any:
        try:
            from piper import PiperVoice
        except ImportError as exc:  # pragma: no cover
            raise NotConfigured("piper-tts is not installed (uv sync --extra tts on the brain host)") from exc
        if not self.voice_path.is_file() or not self.voice_path.with_suffix(".onnx.json").is_file():
            raise NotConfigured(
                f"Piper voice {self.voice!r} not found in {self.voices_dir}. Download it with: "
                f"python3 -m piper.download_voices {self.voice} --data-dir {self.voices_dir}"
            )
        return PiperVoice.load(str(self.voice_path))

    async def _ensure(self) -> Any:
        if self._voice is None:
            async with self._lock:
                if self._voice is None:
                    self._voice = await asyncio.to_thread(self._load)
        return self._voice

    def _config(self) -> Any:
        from piper import SynthesisConfig

        return SynthesisConfig(length_scale=self.length_scale)

    async def synthesize(self, text: str) -> AudioClip:
        voice = await self._ensure()

        def run() -> AudioClip:
            pcm = bytearray()
            rate, width, channels = 22050, 2, 1
            try:
                for chunk in voice.synthesize(text, self._config()):
                    rate, width, channels = chunk.sample_rate, chunk.sample_width, chunk.sample_channels
                    pcm += chunk.audio_int16_bytes
            except Exception as exc:  # noqa: BLE001
                raise UpstreamError(f"piper synthesis failed: {exc.__class__.__name__}") from exc
            return AudioClip(sample_rate=rate, channels=channels, sample_width=width, pcm=bytes(pcm), provider=self.name, voice=self.voice)

        return await asyncio.to_thread(run)

    async def stream(self, text: str) -> AsyncIterator[AudioClip]:
        for sentence in [s.strip() for s in text.replace("?", "?|").replace("!", "!|").replace(".", ".|").split("|") if s.strip()]:
            yield await self.synthesize(sentence)

    async def health(self) -> DependencyStatus:
        try:
            import piper  # noqa: F401
        except ImportError:
            return DependencyStatus(name="tts", status="down", detail="piper-tts not installed")
        if not self.voice_path.is_file():
            return DependencyStatus(name="tts", status="down", detail=f"voice {self.voice} missing in {self.voices_dir}")
        return DependencyStatus(name="tts", status="ok" if self._voice is not None else "degraded", detail=f"piper voice {self.voice}" + ("" if self._voice else " (loads on first use)"))
