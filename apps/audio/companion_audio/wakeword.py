"""Wake-word detection hooks. Off by default; push-to-talk is the primary input.

``OpenWakeWordDetector`` wraps the openWakeWord package (optional extra ``wakeword``);
``ScriptedDetector`` triggers after N chunks for tests. Detectors only see 80 ms PCM chunks
from an in-memory ring; nothing is stored.
"""

from __future__ import annotations

from typing import Any, Protocol


class WakeWordDetector(Protocol):
    name: str

    def feed(self, pcm_chunk: bytes) -> float: ...  # returns the best score for this chunk (0..1)
    def reset(self) -> None: ...


class ScriptedDetector:
    name = "scripted"

    def __init__(self, trigger_after_chunks: int) -> None:
        self.trigger_after = trigger_after_chunks
        self.seen = 0

    def feed(self, pcm_chunk: bytes) -> float:
        self.seen += 1
        return 1.0 if self.seen >= self.trigger_after else 0.0

    def reset(self) -> None:
        self.seen = 0


class OpenWakeWordDetector:
    name = "openwakeword"

    def __init__(self, model: str = "hey_jarvis", threshold: float = 0.6) -> None:
        try:
            import numpy as np
            from openwakeword.model import Model
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("openwakeword is not installed (uv sync --extra wakeword) ") from exc
        self._np = np
        self.threshold = threshold
        self.model_name = model
        self._model: Any = Model(wakeword_models=[model], inference_framework="onnx")

    def feed(self, pcm_chunk: bytes) -> float:
        frame = self._np.frombuffer(pcm_chunk, dtype=self._np.int16)
        scores = self._model.predict(frame)
        return float(max(scores.values())) if scores else 0.0

    def reset(self) -> None:
        self._model.reset()


def build_detector(provider: str, model: str, threshold: float) -> WakeWordDetector | None:
    if provider == "openwakeword":
        return OpenWakeWordDetector(model, threshold)
    if provider == "scripted":
        return ScriptedDetector(trigger_after_chunks=int(threshold) if threshold >= 1 else 5)
    return None
