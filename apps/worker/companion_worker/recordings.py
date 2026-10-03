"""Meeting recordings: explicit, participant-aware, chunked, crash-tolerant.

Audio arrives as complete WAV chunks (each written atomically: temp file then rename), so a
crash loses at most the chunk in flight. Transcription keeps a resume point
(``transcribed_through``) and segment inserts are idempotent, so a re-run never duplicates.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import wave
from pathlib import Path
from typing import Any, Literal

from companion_core.clock import Clock, SystemClock, iso, parse_iso
from companion_core.db import Database
from companion_core.errors import Conflict, NotFound, ValidationFailed
from companion_core.ids import new_id
from pydantic import BaseModel, ConfigDict

RecordingStatus = Literal["recording", "paused", "stopped", "processing", "done", "failed", "cancelled"]


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    client_id: str
    title: str
    status: RecordingStatus
    participants_informed: bool
    route: str
    started_at: str
    paused_at: str | None
    paused_total_ms: int
    stopped_at: str | None
    sample_rate: int
    channels: int
    dir: str
    chunk_count: int
    bytes: int
    audio_ms: int
    transcribed_through: int
    transcript_document_id: str | None
    summary_document_id: str | None
    error: str | None
    created_at: str
    updated_at: str


class RecordingChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recording_id: str
    seq: int
    path: str
    bytes: int
    sha256: str
    start_ms: int
    duration_ms: int
    received_at: str


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recording_id: str
    chunk_seq: int
    seq: int
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None
    confidence: float | None


class RecordingStore:
    def __init__(self, db: Database, media_dir: Path, clock: Clock | None = None) -> None:
        self.db = db
        self.media_dir = Path(media_dir)
        self.clock = clock or SystemClock()

    def _now(self) -> str:
        return iso(self.clock.now())

    @staticmethod
    def _row(r: Any) -> Recording:
        d = {k: r[k] for k in Recording.model_fields}
        d["participants_informed"] = bool(d["participants_informed"])
        return Recording(**d)

    # -- lifecycle -------------------------------------------------------
    def create(self, *, client_id: str, title: str, participants_informed: bool, route: str = "personal") -> Recording:
        if not participants_informed:
            raise ValidationFailed("Recording requires confirmation that everyone present knows it is being recorded.")
        if route not in {"personal", "employer_approved"}:
            raise ValidationFailed("route must be 'personal' or 'employer_approved'")
        if self.active_for(client_id) is not None:
            raise Conflict("a recording is already in progress for this client; stop it first")
        now = self._now()
        rid = new_id("rec")
        rec_dir = self.media_dir / "recordings" / rid
        rec_dir.mkdir(parents=True, exist_ok=True)
        self.db.execute(
            "INSERT INTO recordings(id, client_id, title, status, participants_informed, route, started_at, dir, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, client_id, title[:200], "recording", 1, route, now, str(rec_dir), now, now),
        )
        return self.get(rid)

    def get(self, recording_id: str, *, client_id: str | None = None) -> Recording:
        row = self.db.query_one("SELECT * FROM recordings WHERE id = ?", (recording_id,))
        if not row or (client_id is not None and row["client_id"] != client_id):
            raise NotFound(f"recording {recording_id} not found")
        return self._row(row)

    def list(self, *, client_id: str | None = None, status: list[str] | None = None, limit: int = 50) -> list[Recording]:
        sql = "SELECT * FROM recordings WHERE 1=1"
        params: list[Any] = []
        if client_id is not None:
            sql += " AND client_id = ?"
            params.append(client_id)
        if status:
            sql += f" AND status IN ({','.join('?' * len(status))})"
            params += status
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return [self._row(r) for r in self.db.query(sql, tuple(params))]

    def active_for(self, client_id: str) -> Recording | None:
        row = self.db.query_one("SELECT * FROM recordings WHERE client_id = ? AND status IN ('recording','paused') ORDER BY started_at DESC LIMIT 1", (client_id,))
        return self._row(row) if row else None

    def find_by_title(self, client_id: str, text: str) -> list[Recording]:
        words = [w for w in text.lower().split() if len(w) > 2]
        rows = self.db.query("SELECT * FROM recordings WHERE client_id = ? AND status IN ('done','processing','stopped','failed') ORDER BY started_at DESC LIMIT 200", (client_id,))
        out = []
        for r in rows:
            title = (r["title"] or "").lower()
            if words and all(w in title for w in words):
                out.append(self._row(r))
        if not out and words:
            out = [self._row(r) for r in rows if any(w in (r["title"] or "").lower() for w in words)]
        return out

    def _transition(self, recording_id: str, allowed: set[str], new_status: str, **extra: Any) -> Recording:
        rec = self.get(recording_id)
        if rec.status not in allowed:
            raise Conflict(f"recording is {rec.status}; cannot change to {new_status}")
        now = self._now()
        sets = ["status = ?", "updated_at = ?"]
        params: list[Any] = [new_status, now]
        for k, v in extra.items():
            sets.append(f"{k} = ?")
            params.append(v)
        params.append(recording_id)
        self.db.execute(f"UPDATE recordings SET {', '.join(sets)} WHERE id = ?", tuple(params))  # noqa: S608 - fixed column names
        return self.get(recording_id)

    def pause(self, recording_id: str) -> Recording:
        return self._transition(recording_id, {"recording"}, "paused", paused_at=self._now())

    def resume(self, recording_id: str) -> Recording:
        rec = self.get(recording_id)
        if rec.status != "paused":
            raise Conflict(f"recording is {rec.status}; only a paused recording can resume")
        paused_ms = int((self.clock.now() - parse_iso(rec.paused_at)).total_seconds() * 1000) if rec.paused_at else 0
        return self._transition(recording_id, {"paused"}, "recording", paused_at=None, paused_total_ms=rec.paused_total_ms + paused_ms)

    def stop(self, recording_id: str) -> Recording:
        rec = self.get(recording_id)
        extra: dict[str, Any] = {"stopped_at": self._now()}
        if rec.status == "paused" and rec.paused_at:
            extra["paused_total_ms"] = rec.paused_total_ms + int((self.clock.now() - parse_iso(rec.paused_at)).total_seconds() * 1000)
            extra["paused_at"] = None
        return self._transition(recording_id, {"recording", "paused"}, "stopped", **extra)

    def cancel(self, recording_id: str) -> Recording:
        return self._transition(recording_id, {"recording", "paused", "stopped", "failed"}, "cancelled", stopped_at=self._now())

    def set_status(self, recording_id: str, status: RecordingStatus, *, error: str | None = None) -> Recording:
        now = self._now()
        self.db.execute("UPDATE recordings SET status = ?, error = ?, updated_at = ? WHERE id = ?", (status, error, now, recording_id))
        return self.get(recording_id)

    # -- audio chunks ----------------------------------------------------
    def add_chunk(self, recording_id: str, seq: int, wav_bytes: bytes, *, sha256_expected: str | None = None, client_id: str | None = None) -> RecordingChunk:
        rec = self.get(recording_id, client_id=client_id)
        if rec.status not in {"recording", "paused"}:
            raise Conflict(f"recording is {rec.status}; it no longer accepts audio")
        digest = hashlib.sha256(wav_bytes).hexdigest()
        if sha256_expected and sha256_expected.lower() != digest:
            raise ValidationFailed("chunk checksum mismatch: upload was corrupted or truncated; resend it")
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as w:
                sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        except Exception as exc:  # noqa: BLE001 - wave raises several exception types for bad headers
            raise ValidationFailed(f"chunk is not a valid WAV file: {exc.__class__.__name__}") from exc
        if sr != rec.sample_rate or ch != rec.channels:
            raise ValidationFailed(f"chunk must be {rec.sample_rate} Hz, {rec.channels} channel(s); got {sr} Hz, {ch}")
        duration_ms = int(n * 1000 / sr)
        with self.db.transaction() as conn:
            existing = conn.execute("SELECT * FROM recording_chunks WHERE recording_id = ? AND seq = ?", (recording_id, seq)).fetchone()
            if existing:
                if existing["sha256"] == digest:
                    return RecordingChunk(**{k: existing[k] for k in RecordingChunk.model_fields})
                raise Conflict(f"chunk {seq} was already stored with different content")
            if seq != rec.chunk_count:
                raise Conflict(f"expected chunk {rec.chunk_count} next, got {seq}")
            path = Path(rec.dir) / f"chunk_{seq:05d}.wav"
            tmp = path.with_suffix(".wav.part")
            tmp.write_bytes(wav_bytes)
            with open(tmp, "rb") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp, path)  # atomic: a crash leaves either nothing or a complete chunk
            now = self._now()
            conn.execute(
                "INSERT INTO recording_chunks(recording_id, seq, path, bytes, sha256, start_ms, duration_ms, received_at) VALUES (?,?,?,?,?,?,?,?)",
                (recording_id, seq, str(path), len(wav_bytes), digest, rec.audio_ms, duration_ms, now),
            )
            conn.execute(
                "UPDATE recordings SET chunk_count = chunk_count + 1, bytes = bytes + ?, audio_ms = audio_ms + ?, updated_at = ? WHERE id = ?",
                (len(wav_bytes), duration_ms, now, recording_id),
            )
        return RecordingChunk(recording_id=recording_id, seq=seq, path=str(path), bytes=len(wav_bytes), sha256=digest, start_ms=rec.audio_ms, duration_ms=duration_ms, received_at=now)

    def chunks(self, recording_id: str) -> list[RecordingChunk]:
        rows = self.db.query("SELECT * FROM recording_chunks WHERE recording_id = ? ORDER BY seq", (recording_id,))
        return [RecordingChunk(**{k: r[k] for k in RecordingChunk.model_fields}) for r in rows]

    def chunk_bytes(self, recording_id: str, seq: int) -> bytes:
        row = self.db.query_one("SELECT path FROM recording_chunks WHERE recording_id = ? AND seq = ?", (recording_id, seq))
        if not row:
            raise NotFound(f"chunk {seq} not found")
        return Path(row["path"]).read_bytes()

    # -- transcript ------------------------------------------------------
    def add_segments(self, recording_id: str, chunk_seq: int, segments: list[dict[str, Any]]) -> int:
        """Idempotent: (recording, chunk, seq) is unique, so re-running a chunk inserts nothing new."""
        now = self._now()
        n = 0
        with self.db.transaction() as conn:
            for s in segments:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO transcript_segments(id, recording_id, chunk_seq, seq, start_ms, end_ms, text, speaker, confidence, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (new_id("seg"), recording_id, chunk_seq, int(s["seq"]), int(s["start_ms"]), int(s["end_ms"]), str(s["text"]), s.get("speaker"), s.get("confidence"), now),
                )
                n += cur.rowcount
        return n

    def set_transcribed_through(self, recording_id: str, seq: int) -> None:
        self.db.execute("UPDATE recordings SET transcribed_through = ?, updated_at = ? WHERE id = ?", (seq, self._now(), recording_id))

    def segments(self, recording_id: str) -> list[Segment]:
        rows = self.db.query("SELECT * FROM transcript_segments WHERE recording_id = ? ORDER BY start_ms, chunk_seq, seq", (recording_id,))
        return [Segment(**{k: r[k] for k in Segment.model_fields}) for r in rows]

    def set_documents(self, recording_id: str, *, transcript_document_id: str | None = None, summary_document_id: str | None = None) -> None:
        now = self._now()
        if transcript_document_id:
            self.db.execute("UPDATE recordings SET transcript_document_id = ?, updated_at = ? WHERE id = ?", (transcript_document_id, now, recording_id))
        if summary_document_id:
            self.db.execute("UPDATE recordings SET summary_document_id = ?, updated_at = ? WHERE id = ?", (summary_document_id, now, recording_id))

    def delete(self, recording_id: str) -> dict[str, Any]:
        rec = self.get(recording_id)
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM transcript_segments WHERE recording_id = ?", (recording_id,))
            conn.execute("DELETE FROM recording_chunks WHERE recording_id = ?", (recording_id,))
            conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
        shutil.rmtree(rec.dir, ignore_errors=True)
        return {"deleted": True, "transcript_document_id": rec.transcript_document_id, "summary_document_id": rec.summary_document_id,
                "note": json.dumps({"files_removed": True, "backups": "earlier backups keep the audio until they rotate"})}
