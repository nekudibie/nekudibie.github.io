"""VaultService: the only code that touches vault.db.

Originals in ``documents`` are authoritative; ``chunks`` and the FTS index are
derived and can be rebuilt with ``rebuild_index()``. Corrections create a new
revision linked by ``supersedes_id`` so history is retained while the current
record is unambiguous. Deletion removes chunks (and so the index) immediately and
blanks the original text, leaving a tombstone for audit.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from companion_contracts.common import Anchor, Provenance
from companion_contracts.vault import (
    CorrectionRequest,
    DeleteResponse,
    Document,
    DocumentImport,
    NoteCreate,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from companion_core.clock import Clock, SystemClock, iso
from companion_core.db import Database
from companion_core.errors import Conflict, NotFound, ValidationFailed
from companion_core.ids import new_id
from companion_core.logging import get_logger

from .chunking import chunk_text
from .fts import fts_query, keyword_terms
from .structured import StructuredMemory

log = get_logger(__name__)
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VaultService:
    def __init__(
        self,
        db: Database,
        *,
        chunk_chars: int = 1200,
        chunk_overlap_chars: int = 150,
        clock: Clock | None = None,
    ) -> None:
        self.db = db
        self.chunk_chars = chunk_chars
        self.chunk_overlap = chunk_overlap_chars
        self.clock = clock or SystemClock()
        self.structured = StructuredMemory(db, clock=self.clock)

    # -- lifecycle -------------------------------------------------------
    def migrate(self) -> list[str]:
        return self.db.migrate(MIGRATIONS_DIR)

    def _now(self) -> str:
        return iso(self.clock.now())

    def _audit(self, conn: sqlite3.Connection, actor: str, action: str, target: str | None, **details: Any) -> None:
        conn.execute(
            "INSERT INTO audit_log(at, actor, action, target_id, details_json) VALUES (?,?,?,?,?)",
            (self._now(), actor, action, target, json.dumps(details, default=str)),
        )

    # -- writes ----------------------------------------------------------
    def create_note(self, note: NoteCreate, *, actor: str) -> Document:
        prov = note.provenance or Provenance(source_type="note", captured_by=actor, trust="owner_stated")
        imp = DocumentImport(
            title=note.title or _default_title(note.text),
            text=note.text,
            kind=note.kind,
            scope=note.scope,
            project=note.project,
            provenance=prov,
            metadata=note.metadata,
        )
        return self.import_document(imp, actor=actor)

    def import_document(self, imp: DocumentImport, *, actor: str) -> Document:
        text = imp.text.replace("\r\n", "\n")
        digest = _sha(text)
        now = self._now()
        with self.db.transaction() as conn:
            if imp.idempotency_key:
                row = conn.execute(
                    "SELECT id, content_sha256 FROM documents WHERE idempotency_key = ?", (imp.idempotency_key,)
                ).fetchone()
                if row:
                    if row["content_sha256"] == digest:
                        return self.get_document(row["id"], scopes=None)
                    raise Conflict(
                        f"idempotency key {imp.idempotency_key!r} already used with different content",
                        details={"document_id": row["id"]},
                    )
            doc_id = new_id("doc")
            prov = imp.provenance
            conn.execute(
                """INSERT INTO documents(id, kind, title, text, mime_type, scope, project, source_type, source_ref,
                       source_uri, captured_by, captured_at, trust, content_sha256, revision, idempotency_key,
                       metadata_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
                (
                    doc_id, imp.kind, imp.title[:300], text, imp.mime_type, imp.scope, imp.project,
                    prov.source_type, prov.source_ref, prov.source_uri, prov.captured_by or actor,
                    prov.captured_at or now, prov.trust, digest, imp.idempotency_key,
                    json.dumps(imp.metadata, default=str), now, now,
                ),
            )
            if imp.segments:
                n = self._write_segment_chunks(conn, doc_id, imp.title, text, imp.segments)
            else:
                n = self._write_chunks(conn, doc_id, imp.title, text)
            self._audit(conn, actor, "import", doc_id, kind=imp.kind, chunks=n, source_type=prov.source_type)
        return self.get_document(doc_id, scopes=None)

    def _write_chunks(self, conn: sqlite3.Connection, doc_id: str, title: str, text: str) -> int:
        pieces = chunk_text(text, chunk_chars=self.chunk_chars, overlap_chars=self.chunk_overlap)
        for c in pieces:
            anchor = Anchor(kind="offset", start=c.start, end=c.end, paragraph=c.paragraph)
            conn.execute(
                "INSERT INTO chunks(id, document_id, seq, text, title, anchor_json) VALUES (?,?,?,?,?,?)",
                (new_id("chk"), doc_id, c.seq, c.text, title, anchor.model_dump_json(exclude_none=True)),
            )
        return len(pieces)

    def _write_segment_chunks(self, conn: sqlite3.Connection, doc_id: str, title: str, text: str, segments: list[Any]) -> int:
        """Group consecutive segments into chunks; anchors keep the first segment id and time span
        plus the character offsets of the group within the stored document text."""
        groups: list[list[Any]] = []
        cur: list[Any] = []
        size = 0
        for seg in segments:
            if cur and size + len(seg.text) > self.chunk_chars:
                groups.append(cur)
                cur, size = [], 0
            cur.append(seg)
            size += len(seg.text) + 1
        if cur:
            groups.append(cur)
        pos = 0
        n = 0
        for seq, group in enumerate(groups):
            body = " ".join(g.text.strip() for g in group)
            start = text.find(group[0].text.strip(), pos)
            if start < 0:
                start = pos
            last = group[-1].text.strip()
            end_idx = text.find(last, start)
            end = (end_idx + len(last)) if end_idx >= 0 else min(len(text), start + len(body))
            pos = end
            anchor = Anchor(kind="segment", segment_id=group[0].id, start_time_s=group[0].start_s, end_time_s=group[-1].end_s, page=group[0].page, start=start, end=end)
            conn.execute(
                "INSERT INTO chunks(id, document_id, seq, text, title, anchor_json) VALUES (?,?,?,?,?,?)",
                (new_id("chk"), doc_id, seq, body, title, anchor.model_dump_json(exclude_none=True)),
            )
            n += 1
        return n

    def correct(self, document_id: str, req: CorrectionRequest, *, actor: str, scopes: Iterable[str] | None) -> Document:
        old = self.get_document(document_id, scopes=scopes)
        if old.deleted_at:
            raise Conflict("cannot correct a deleted record")
        if old.superseded_by_id:
            raise Conflict("this record was already corrected", details={"current_id": self._current_id(old.id)})
        text = req.new_text.replace("\r\n", "\n")
        now = self._now()
        new_doc_id = new_id("doc")
        with self.db.transaction() as conn:
            prov = old.provenance
            meta = dict(old.metadata)
            meta["correction_reason"] = req.reason
            conn.execute(
                """INSERT INTO documents(id, kind, title, text, mime_type, scope, project, source_type, source_ref,
                       source_uri, captured_by, captured_at, trust, content_sha256, revision, supersedes_id,
                       metadata_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_doc_id, old.kind, (req.title or old.title)[:300], text, old.mime_type, old.scope, old.project,
                    prov.source_type, prov.source_ref, prov.source_uri, actor, now, "owner_stated",
                    _sha(text), old.revision + 1, old.id, json.dumps(meta, default=str), now, now,
                ),
            )
            conn.execute(
                "UPDATE documents SET superseded_by_id = ?, updated_at = ? WHERE id = ?", (new_doc_id, now, old.id)
            )
            self._write_chunks(conn, new_doc_id, req.title or old.title, text)
            self._audit(conn, actor, "correct", old.id, new_id=new_doc_id, reason=req.reason)
        return self.get_document(new_doc_id, scopes=None)

    def delete(self, document_id: str, *, actor: str, scopes: Iterable[str] | None, reason: str = "") -> DeleteResponse:
        doc = self.get_document(document_id, scopes=scopes)
        now = self._now()
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            removed = cur.rowcount
            conn.execute(
                "UPDATE documents SET text = NULL, deleted_at = ?, updated_at = ? WHERE id = ?",
                (now, now, document_id),
            )
            self._audit(conn, actor, "delete", document_id, reason=reason, chunks_removed=removed)
        note = (
            "Original text and search index entries removed now. Tombstone (title, hash, timestamps) kept for audit. "
            "Backups taken before this deletion still contain the record until they are rotated (see docs/OPERATIONS.md)."
        )
        return DeleteResponse(document_id=doc.id, deleted=True, chunks_removed=removed, note=note)

    # -- reads -----------------------------------------------------------
    def _row_to_document(self, row: sqlite3.Row) -> Document:
        return Document(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            text=row["text"],
            mime_type=row["mime_type"],
            scope=row["scope"],
            project=row["project"],
            provenance=Provenance(
                source_type=row["source_type"],
                source_ref=row["source_ref"],
                source_uri=row["source_uri"],
                captured_by=row["captured_by"],
                captured_at=row["captured_at"],
                trust=row["trust"],
            ),
            content_sha256=row["content_sha256"],
            revision=row["revision"],
            supersedes_id=row["supersedes_id"],
            superseded_by_id=row["superseded_by_id"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    def get_document(self, document_id: str, *, scopes: Iterable[str] | None) -> Document:
        row = self.db.query_one("SELECT * FROM documents WHERE id = ?", (document_id,))
        if not row or (scopes is not None and row["scope"] not in set(scopes)):
            raise NotFound(f"document {document_id} not found")
        return self._row_to_document(row)

    def _current_id(self, document_id: str) -> str:
        cur = document_id
        for _ in range(100):
            row = self.db.query_one("SELECT superseded_by_id FROM documents WHERE id = ?", (cur,))
            if not row or not row["superseded_by_id"]:
                return cur
            cur = row["superseded_by_id"]
        return cur

    def history(self, document_id: str, *, scopes: Iterable[str] | None) -> list[Document]:
        """All revisions of a record, oldest first."""
        doc = self.get_document(document_id, scopes=scopes)
        root = doc
        while root.supersedes_id:
            root = self.get_document(root.supersedes_id, scopes=None)
        chain = [root]
        while chain[-1].superseded_by_id:
            chain.append(self.get_document(chain[-1].superseded_by_id, scopes=None))
        return chain

    def list_documents(
        self,
        *,
        scopes: Iterable[str],
        kinds: list[str] | None = None,
        project: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        include_superseded: bool = False,
    ) -> list[Document]:
        scopes = list(scopes)
        if not scopes:
            return []
        sql = f"SELECT * FROM documents WHERE scope IN ({','.join('?' * len(scopes))})"  # noqa: S608 - placeholders only
        params: list[Any] = list(scopes)
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += kinds
        if project:
            sql += " AND project = ?"
            params.append(project)
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        if not include_superseded:
            sql += " AND superseded_by_id IS NULL"
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [max(1, min(limit, 500)), max(0, offset)]
        return [self._row_to_document(r) for r in self.db.query(sql, tuple(params))]

    def get_chunk(self, chunk_id: str, *, scopes: Iterable[str] | None) -> dict[str, Any]:
        row = self.db.query_one(
            "SELECT c.*, d.scope FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ?", (chunk_id,)
        )
        if not row or (scopes is not None and row["scope"] not in set(scopes)):
            raise NotFound(f"chunk {chunk_id} not found")
        return {
            "id": row["id"],
            "document_id": row["document_id"],
            "seq": row["seq"],
            "text": row["text"],
            "anchor": json.loads(row["anchor_json"]),
        }

    # -- search ----------------------------------------------------------
    def search(self, req: SearchRequest, *, scopes: Iterable[str]) -> SearchResponse:
        allowed = [s for s in req.scopes if s in set(scopes)]
        if not allowed:
            return SearchResponse(query=req.query, hits=[], total_candidates=0, strategy="no_scope")
        terms = keyword_terms(req.query)
        if not terms:
            return SearchResponse(query=req.query, hits=[], total_candidates=0, strategy="empty_query")

        for strategy, mode in (("fts_and", "AND"), ("fts_or", "OR")):
            match = fts_query(terms, mode=mode)
            rows = self._fts_rows(match, req, allowed)
            if rows:
                hits = [self._row_to_hit(r) for r in rows[: req.limit]]
                return SearchResponse(query=req.query, hits=hits, total_candidates=len(rows), strategy=strategy)
            if len(terms) == 1:
                break
        return SearchResponse(query=req.query, hits=[], total_candidates=0, strategy="none")

    def _fts_rows(self, match: str, req: SearchRequest, scopes: Sequence[str]) -> list[sqlite3.Row]:
        sql = f"""
            SELECT c.id AS chunk_id, c.document_id, c.seq, c.text AS chunk_text, c.anchor_json,
                   d.kind, d.title, d.source_type, d.source_ref, d.source_uri, d.captured_by, d.captured_at, d.trust,
                   d.created_at, d.revision, d.superseded_by_id,
                   bm25(chunks_fts, 1.0, 3.0) AS rank,
                   snippet(chunks_fts, 0, '[', ']', ' … ', 24) AS snip
            FROM chunks_fts
            JOIN chunks c ON c.rid = chunks_fts.rowid
            JOIN documents d ON d.id = c.document_id
            WHERE chunks_fts MATCH ?
              AND d.deleted_at IS NULL
              AND d.scope IN ({','.join('?' * len(scopes))})
        """  # noqa: S608 - only '?' placeholders are interpolated
        params: list[Any] = [match, *scopes]
        if req.kinds:
            sql += f" AND d.kind IN ({','.join('?' * len(req.kinds))})"
            params += list(req.kinds)
        if req.project:
            sql += " AND d.project = ?"
            params.append(req.project)
        if not req.include_superseded:
            sql += " AND d.superseded_by_id IS NULL"
        if req.since:
            sql += " AND d.created_at >= ?"
            params.append(req.since)
        if req.document_ids:
            sql += f" AND d.id IN ({','.join('?' * len(req.document_ids))})"
            params += list(req.document_ids)
        sql += " ORDER BY rank, d.created_at DESC LIMIT ?"
        params.append(max(req.limit * 4, 20))
        try:
            return self.db.query(sql, tuple(params))
        except sqlite3.OperationalError as exc:
            if "fts5" in str(exc).lower() or "syntax" in str(exc).lower():
                raise ValidationFailed(f"search query could not be parsed: {exc}") from exc
            raise

    def _row_to_hit(self, r: sqlite3.Row) -> SearchHit:
        return SearchHit(
            document_id=r["document_id"],
            chunk_id=r["chunk_id"],
            title=r["title"],
            kind=r["kind"],
            snippet=r["snip"],
            text=r["chunk_text"],
            score=float(-r["rank"]),  # bm25 is negative-better; flip so higher is better
            anchor=Anchor.model_validate(json.loads(r["anchor_json"])),
            provenance=Provenance(
                source_type=r["source_type"],
                source_ref=r["source_ref"],
                source_uri=r["source_uri"],
                captured_by=r["captured_by"],
                captured_at=r["captured_at"],
                trust=r["trust"],
            ),
            created_at=r["created_at"],
            revision=r["revision"],
            is_current=r["superseded_by_id"] is None,
        )

    # -- maintenance -----------------------------------------------------
    def rebuild_index(self) -> int:
        """Drop and rebuild all chunks + FTS from the authoritative originals."""
        n = 0
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM chunks")
            rows = conn.execute(
                "SELECT id, title, text FROM documents WHERE deleted_at IS NULL AND text IS NOT NULL"
            ).fetchall()
            for r in rows:
                n += self._write_chunks(conn, r["id"], r["title"], r["text"])
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
        return n

    def stats(self) -> dict[str, Any]:
        docs = self.db.query_one("SELECT COUNT(*) AS n FROM documents WHERE deleted_at IS NULL")
        chunks = self.db.query_one("SELECT COUNT(*) AS n FROM chunks")
        deleted = self.db.query_one("SELECT COUNT(*) AS n FROM documents WHERE deleted_at IS NOT NULL")
        by_kind = self.db.query(
            "SELECT kind, COUNT(*) AS n FROM documents WHERE deleted_at IS NULL AND superseded_by_id IS NULL GROUP BY kind"
        )
        return {
            "documents": docs["n"] if docs else 0,
            "chunks": chunks["n"] if chunks else 0,
            "deleted_tombstones": deleted["n"] if deleted else 0,
            "by_kind": {r["kind"]: r["n"] for r in by_kind},
            "schema_version": self.db.schema_version(),
            "db_path": str(self.db.path),
        }

    def export_jsonl(self, *, scopes: Iterable[str], include_deleted: bool = False) -> Iterator[str]:
        scopes = list(scopes)
        sql = f"SELECT * FROM documents WHERE scope IN ({','.join('?' * len(scopes))})"  # noqa: S608 - placeholders only
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        sql += " ORDER BY created_at"
        for row in self.db.query(sql, tuple(scopes)):
            yield self._row_to_document(row).model_dump_json() + "\n"


def _default_title(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else "Untitled"
    return (first[:77] + "…") if len(first) > 80 else first
