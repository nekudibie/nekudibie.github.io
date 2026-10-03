"""Audio capture and playback backends for Linux.

``arecord``/``aplay`` (alsa-utils) are used rather than a compiled PortAudio binding so
the desk Pi install stays apt-only. File and null backends exist for tests and for
hardware-less runs. Capture buffers live in memory only.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Protocol

from companion_core.logging import get_logger

log = get_logger(__name__)

RATE = 16000
CHANNELS = 1
WIDTH = 2
CHUNK_FRAMES = 1280  # 80 ms at 16 kHz


class CaptureBackend(Protocol):
    def start(self) -> None: ...
    def read(self, timeout_s: float = 0.2) -> bytes | None: ...  # a PCM chunk, or None when no data yet / ended
    def stop(self) -> None: ...
    def describe(self) -> str: ...


class PlaybackBackend(Protocol):
    def play(self, wav_bytes: bytes) -> None: ...  # non-blocking start
    def is_playing(self) -> bool: ...
    def stop(self) -> None: ...
    def wait(self, timeout_s: float | None = None) -> None: ...
    def describe(self) -> str: ...


class ArecordCapture:
    def __init__(self, device: str | None = None) -> None:
        self.device = device
        self._proc: subprocess.Popen[bytes] | None = None

    def describe(self) -> str:
        return f"arecord{' -D ' + self.device if self.device else ''} 16 kHz mono S16_LE"

    def start(self) -> None:
        if shutil.which("arecord") is None:
            raise RuntimeError("arecord not found: install alsa-utils (sudo apt install alsa-utils)")
        cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(RATE), "-c", str(CHANNELS), "-t", "raw", "-"]
        if self.device:
            cmd[1:1] = ["-D", self.device]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)  # noqa: S603

    def read(self, timeout_s: float = 0.2) -> bytes | None:
        if self._proc is None or self._proc.stdout is None:
            return None
        data = self._proc.stdout.read(CHUNK_FRAMES * WIDTH)
        return data or None

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


class AplayPlayback:
    def __init__(self, device: str | None = None) -> None:
        self.device = device
        self._proc: subprocess.Popen[bytes] | None = None

    def describe(self) -> str:
        return f"aplay{' -D ' + self.device if self.device else ''}"

    def play(self, wav_bytes: bytes) -> None:
        if shutil.which("aplay") is None:
            raise RuntimeError("aplay not found: install alsa-utils (sudo apt install alsa-utils)")
        self.stop()
        cmd = ["aplay", "-q", "-"]
        if self.device:
            cmd[1:1] = ["-D", self.device]
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)  # noqa: S603

        def feed(proc: subprocess.Popen[bytes], data: bytes) -> None:
            try:
                assert proc.stdin is not None
                proc.stdin.write(data)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        threading.Thread(target=feed, args=(self._proc, wav_bytes), daemon=True).start()

    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def wait(self, timeout_s: float | None = None) -> None:
        if self._proc is not None:
            try:
                self._proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                pass


class FileCapture:
    """Replays a WAV file as if spoken (tests, and `companion-audio --simulate`)."""

    def __init__(self, path: Path, *, realtime: bool = False) -> None:
        self.path = path
        self.realtime = realtime
        self._pcm = b""
        self._pos = 0
        self.comment: str | None = None

    def describe(self) -> str:
        return f"file {self.path}"

    def start(self) -> None:
        data = self.path.read_bytes()
        with wave.open(io.BytesIO(data), "rb") as w:
            if w.getframerate() != RATE or w.getnchannels() != CHANNELS or w.getsampwidth() != WIDTH:
                raise RuntimeError(f"{self.path} must be 16 kHz mono 16-bit (got {w.getframerate()} Hz, {w.getnchannels()} ch)")
            self._pcm = w.readframes(w.getnframes())
        from companion_integrations.speech.base import inspect_wav

        self.comment = inspect_wav(data).comment
        self._pos = 0

    def read(self, timeout_s: float = 0.2) -> bytes | None:
        if self._pos >= len(self._pcm):
            return None
        chunk = self._pcm[self._pos : self._pos + CHUNK_FRAMES * WIDTH]
        self._pos += len(chunk)
        if self.realtime:
            time.sleep(CHUNK_FRAMES / RATE)
        return chunk

    def stop(self) -> None:
        pass


class NullPlayback:
    """Records what would have been played; optional simulated duration for barge-in tests."""

    def __init__(self, *, simulate_duration: bool = False) -> None:
        self.played: list[bytes] = []
        self.stopped = 0
        self.simulate_duration = simulate_duration
        self._until = 0.0

    def describe(self) -> str:
        return "null playback"

    def play(self, wav_bytes: bytes) -> None:
        self.played.append(wav_bytes)
        if self.simulate_duration:
            with wave.open(io.BytesIO(wav_bytes), "rb") as w:
                self._until = time.monotonic() + w.getnframes() / w.getframerate()

    def is_playing(self) -> bool:
        return self.simulate_duration and time.monotonic() < self._until

    def stop(self) -> None:
        if self.is_playing():
            self.stopped += 1
        self._until = 0.0

    def wait(self, timeout_s: float | None = None) -> None:
        while self.is_playing():
            time.sleep(0.01)
