"""faster-whisper adapter (CTranslate2 Whisper). Optional dependency: ``companion-integrations[stt]``.

Verified API (docs/SOURCES.md): ``WhisperModel(size, device, compute_type)``;
``model.transcribe(audio, language=..., vad_filter=..., beam_size=...)`` returns
``(segments, info)`` where each segment has ``start``, ``end``, ``text`` and
``avg_logprob``. The model is loaded lazily in a worker thread; the first call downloads
weights from Hugging Face unless ``download_root`` already holds them.
"""

from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path
from typing import Any

from companion_contracts.health import DependencyStatus
from companion_core.errors import NotConfigured, UpstreamError, ValidationFailed
from companion_core.logging import get_logger

from .base import Transcript, TranscriptSegment, inspect_wav

log = get_logger(__name__)


class FasterWhisperSTT:
    name = "faster_whisper"
    is_fixture = False

    def __init__(self, model: str = "base", *, device: str = "cpu", compute_type: str = "int8", cpu_threads: int = 0, download_root: Path | None = None, language: str | None = "en", max_audio_s: float = 120.0) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.download_root = download_root
        self.language = language
        self.max_audio_s = max_audio_s
        self._model: Any = None
        self._lock = asyncio.Lock()
        self._load_error: str | None = None

    def _load(self) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise NotConfigured("faster-whisper is not installed (uv sync --extra stt on the brain host)") from exc
        kwargs: dict[str, Any] = {"device": self.device, "compute_type": self.compute_type}
        if self.cpu_threads:
            kwargs["cpu_threads"] = self.cpu_threads
        if self.download_root:
            kwargs["download_root"] = str(self.download_root)
        return WhisperModel(self.model, **kwargs)

    async def _ensure(self) -> Any:
        if self._model is None:
            async with self._lock:
                if self._model is None:
                    try:
                        self._model = await asyncio.to_thread(self._load)
                    except NotConfigured:
                        raise
                    except Exception as exc:  # noqa: BLE001 - model download/load failures are upstream problems
                        self._load_error = f"{exc.__class__.__name__}: {str(exc)[:200]}"
                        raise UpstreamError(f"could not load whisper model {self.model!r}: {self._load_error}") from exc
        return self._model

    async def transcribe(self, wav_bytes: bytes, *, language: str | None = None) -> Transcript:
        info = inspect_wav(wav_bytes)
        if info.duration_s > self.max_audio_s:
            raise ValidationFailed(f"audio is {info.duration_s:.0f}s; limit is {self.max_audio_s:.0f}s for interactive transcription")
        model = await self._ensure()
        started = time.monotonic()

        def run() -> tuple[list[TranscriptSegment], str | None, float]:
            segments, meta = model.transcribe(io.BytesIO(wav_bytes), language=language or self.language, vad_filter=True, beam_size=5)
            out = []
            for i, s in enumerate(segments):
                conf = None
                if getattr(s, "avg_logprob", None) is not None:
                    conf = max(0.0, min(1.0, 1.0 + float(s.avg_logprob)))  # rough map of log-prob to 0..1
                out.append(TranscriptSegment(id=i, start_s=float(s.start), end_s=float(s.end), text=s.text.strip(), confidence=conf))
            return out, getattr(meta, "language", None), float(getattr(meta, "duration", info.duration_s))

        segs, lang, dur = await asyncio.to_thread(run)
        return Transcript(
            text=" ".join(s.text for s in segs).strip(), language=lang, duration_s=dur, segments=segs, provider=self.name,
            model=self.model, is_fixture=False, processing_ms=int((time.monotonic() - started) * 1000),
        )

    async def health(self) -> DependencyStatus:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return DependencyStatus(name="stt", status="down", detail="faster-whisper not installed")
        if self._model is not None:
            return DependencyStatus(name="stt", status="ok", detail=f"faster-whisper {self.model} ({self.device}/{self.compute_type}) loaded")
        if self._load_error:
            return DependencyStatus(name="stt", status="down", detail=self._load_error)
        return DependencyStatus(name="stt", status="degraded", detail=f"faster-whisper installed; model {self.model!r} loads on first use (download needs network)")
