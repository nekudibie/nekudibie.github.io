"""Structured memory: facts, projects, decisions, actions, purchases, lesson progress.

Design rules
* Confirmed facts and inferred candidates are different statuses, never mixed in answers.
* Changing a fact or decision supersedes the old row (history retained, current unambiguous).
* Every row names its evidence (document/chunk/message id and quote) so answers can cite it.
* Owners/deadlines on actions stay NULL unless evidence supports them.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from typing import Any, Literal

from companion_core.clock import Clock, SystemClock, iso
from companion_core.db import Database
from companion_core.errors import Conflict, NotFound, ValidationFailed
from companion_core.ids import new_id
from pydantic import BaseModel, ConfigDict, Field

from .fts import fts_query, keyword_terms

FactStatus = Literal["candidate", "confirmed", "retracted", "superseded", "rejected"]


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    subject: str
    predicate: str
    value: str
    status: FactStatus
    confidence: float
    scope: str
    stated_by: str
    trust: str
    evidence_document_id: str | None = None
    evidence_chunk_id: str | None = None
    evidence_message_id: str | None = None
    evidence_quote: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    supersedes_id: str | None = None
    superseded_by_id: str | None = None
    created_at: str
    updated_at: str
    confirmed_at: str | None = None
    retracted_at: str | None = None
    note: str = ""


class FactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=120)
    predicate: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    status: Literal["candidate", "confirmed"] = "confirmed"
    confidence: float = Field(default=1.0, ge=0, le=1)
    scope: str = "owner"
    trust: Literal["owner_stated", "imported", "inferred"] = "owner_stated"
    evidence_document_id: str | None = None
    evidence_chunk_id: str | None = None
    evidence_message_id: str | None = None
    evidence_quote: str | None = Field(default=None, max_length=1000)
    valid_from: str | None = None
    note: str = ""


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    project_id: str | None
    project_name: str | None = None
    statement: str
    rationale: str
    status: Literal["current", "superseded", "reversed"]
    scope: str
    decided_at: str
    stated_by: str
    source_document_id: str | None = None
    source_chunk_id: str | None = None
    supersedes_id: str | None = None
    superseded_by_id: str | None = None
    created_at: str
    updated_at: str


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1, max_length=4000)
    project: str | None = Field(default=None, max_length=120)
    rationale: str = Field(default="", max_length=4000)
    decided_at: str | None = None
    scope: str = "owner"
    source_document_id: str | None = None
    source_chunk_id: str | None = None


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    owner: str | None
    owner_confidence: float
    due_at: str | None
    due_text: str | None
    due_confidence: float
    status: Literal["draft", "open", "done", "cancelled"]
    scope: str
    project_id: str | None = None
    meeting_id: str | None = None
    source_document_id: str | None = None
    source_chunk_id: str | None = None
    source_segment_id: str | None = None
    source_quote: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class ActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    owner: str | None = Field(default=None, max_length=120)
    owner_confidence: float = Field(default=0, ge=0, le=1)
    due_at: str | None = None
    due_text: str | None = Field(default=None, max_length=120)
    due_confidence: float = Field(default=0, ge=0, le=1)
    status: Literal["draft", "open"] = "draft"
    scope: str = "owner"
    project: str | None = None
    meeting_id: str | None = None
    source_document_id: str | None = None
    source_chunk_id: str | None = None
    source_segment_id: str | None = None
    source_quote: str | None = Field(default=None, max_length=1000)


class Purchase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    merchant: str
    order_ref: str
    items: list[dict[str, Any]]
    amount: float | None
    currency: str | None
    ordered_at: str | None
    status: Literal["confirmed", "shipped", "delivered", "cancelled", "refunded"]
    status_history: list[dict[str, Any]]
    scope: str
    source_message_ids: list[str]
    source_document_id: str | None = None
    created_at: str
    updated_at: str


class PurchaseUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant: str = Field(min_length=1, max_length=120)
    order_ref: str = Field(min_length=1, max_length=120)
    items: list[dict[str, Any]] = Field(default_factory=list)
    amount: float | None = None
    currency: str | None = Field(default=None, max_length=8)
    ordered_at: str | None = None
    status: Literal["confirmed", "shipped", "delivered", "cancelled", "refunded"] = "confirmed"
    event_at: str | None = None
    source_message_id: str | None = None
    source_document_id: str | None = None
    scope: str = "owner"


class LessonProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    course_id: str
    lesson_id: str
    status: Literal["not_started", "in_progress", "needs_review", "mastered"]
    attempts: int
    correct: int
    last_score: float | None
    weak_topics: list[str]
    evidence: list[dict[str, Any]]
    updated_at: str


# Status ordering for purchase updates: later events do not regress earlier ones, and the
# terminal states win over anything else.
_PURCHASE_RANK = {"confirmed": 1, "shipped": 2, "delivered": 3, "cancelled": 9, "refunded": 9}


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


class StructuredMemory:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or SystemClock()

    def _now(self) -> str:
        return iso(self.clock.now())

    def _audit(self, conn: sqlite3.Connection, actor: str, action: str, target: str | None, **details: Any) -> None:
        conn.execute(
            "INSERT INTO audit_log(at, actor, action, target_id, details_json) VALUES (?,?,?,?,?)",
            (self._now(), actor, action, target, json.dumps(details, default=str)),
        )

    # ---------------------------------------------------------------- facts
    def _fact(self, row: sqlite3.Row) -> Fact:
        return Fact(**{k: row[k] for k in Fact.model_fields})

    def add_fact(self, f: FactCreate, *, actor: str) -> Fact:
        now = self._now()
        fid = new_id("fact")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO facts(id, subject, predicate, value, status, confidence, scope, stated_by, trust,
                       evidence_document_id, evidence_chunk_id, evidence_message_id, evidence_quote, valid_from,
                       created_at, updated_at, confirmed_at, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    fid, _key(f.subject), _key(f.predicate), f.value.strip(), f.status, f.confidence, f.scope, actor, f.trust,
                    f.evidence_document_id, f.evidence_chunk_id, f.evidence_message_id, f.evidence_quote, f.valid_from or now,
                    now, now, now if f.status == "confirmed" else None, f.note,
                ),
            )
            if f.status == "confirmed":
                self._supersede_other_confirmed(conn, fid, _key(f.subject), _key(f.predicate), now)
            self._audit(conn, actor, "fact.add", fid, status=f.status, subject=f.subject, predicate=f.predicate)
        return self.get_fact(fid)

    def _supersede_other_confirmed(self, conn: sqlite3.Connection, keep_id: str, subject: str, predicate: str, now: str) -> None:
        """A newly confirmed value for (subject, predicate) supersedes earlier confirmed values."""
        rows = conn.execute(
            "SELECT id FROM facts WHERE subject = ? AND predicate = ? AND status = 'confirmed' AND id != ?",
            (subject, predicate, keep_id),
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE facts SET status = 'superseded', superseded_by_id = ?, valid_to = ?, updated_at = ? WHERE id = ?",
                (keep_id, now, now, r["id"]),
            )
        if rows:
            conn.execute("UPDATE facts SET supersedes_id = COALESCE(supersedes_id, ?) WHERE id = ?", (rows[-1]["id"], keep_id))

    def get_fact(self, fact_id: str, *, scopes: Iterable[str] | None = None) -> Fact:
        row = self.db.query_one("SELECT * FROM facts WHERE id = ?", (fact_id,))
        if not row or (scopes is not None and row["scope"] not in set(scopes)):
            raise NotFound(f"fact {fact_id} not found")
        return self._fact(row)

    def confirm_fact(self, fact_id: str, *, actor: str, scopes: Iterable[str] | None = None) -> Fact:
        f = self.get_fact(fact_id, scopes=scopes)
        if f.status not in {"candidate"}:
            raise Conflict(f"fact is {f.status}, only candidates can be confirmed")
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE facts SET status = 'confirmed', confirmed_at = ?, updated_at = ?, trust = 'owner_stated', confidence = 1.0 WHERE id = ?",
                (now, now, fact_id),
            )
            self._supersede_other_confirmed(conn, fact_id, f.subject, f.predicate, now)
            self._audit(conn, actor, "fact.confirm", fact_id)
        return self.get_fact(fact_id)

    def reject_fact(self, fact_id: str, *, actor: str, reason: str = "", scopes: Iterable[str] | None = None) -> Fact:
        f = self.get_fact(fact_id, scopes=scopes)
        if f.status != "candidate":
            raise Conflict("only candidates can be rejected; use retract for confirmed facts")
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute("UPDATE facts SET status = 'rejected', updated_at = ?, note = ? WHERE id = ?", (now, reason, fact_id))
            self._audit(conn, actor, "fact.reject", fact_id, reason=reason)
        return self.get_fact(fact_id)

    def retract_fact(self, fact_id: str, *, actor: str, reason: str = "", scopes: Iterable[str] | None = None) -> Fact:
        f = self.get_fact(fact_id, scopes=scopes)
        if f.status not in {"confirmed", "candidate"}:
            raise Conflict(f"fact is already {f.status}")
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE facts SET status = 'retracted', retracted_at = ?, valid_to = ?, updated_at = ?, note = ? WHERE id = ?",
                (now, now, now, reason, fact_id),
            )
            self._audit(conn, actor, "fact.retract", fact_id, reason=reason)
        return self.get_fact(fact_id)

    def update_fact(self, fact_id: str, new_value: str, *, actor: str, reason: str = "", scopes: Iterable[str] | None = None) -> Fact:
        """'That's changed': confirm a new value that supersedes the old one."""
        old = self.get_fact(fact_id, scopes=scopes)
        if old.status not in {"confirmed", "candidate"}:
            raise Conflict(f"fact is {old.status}; update its current successor instead")
        return self.add_fact(
            FactCreate(subject=old.subject, predicate=old.predicate, value=new_value, status="confirmed", scope=old.scope,
                       trust="owner_stated", note=reason, evidence_message_id=None),
            actor=actor,
        )

    def current_facts(self, *, scopes: Iterable[str], subject: str | None = None, predicate: str | None = None, include_candidates: bool = False) -> list[Fact]:
        scopes = list(scopes)
        if not scopes:
            return []
        statuses = ["confirmed", "candidate"] if include_candidates else ["confirmed"]
        sql = f"SELECT * FROM facts WHERE scope IN ({','.join('?' * len(scopes))}) AND status IN ({','.join('?' * len(statuses))})"  # noqa: S608
        params: list[Any] = [*scopes, *statuses]
        if subject:
            sql += " AND subject = ?"
            params.append(_key(subject))
        if predicate:
            sql += " AND predicate = ?"
            params.append(_key(predicate))
        sql += " ORDER BY subject, predicate, created_at DESC"
        return [self._fact(r) for r in self.db.query(sql, tuple(params))]

    def candidates(self, *, scopes: Iterable[str], limit: int = 50) -> list[Fact]:
        scopes = list(scopes)
        if not scopes:
            return []
        rows = self.db.query(
            f"SELECT * FROM facts WHERE status = 'candidate' AND scope IN ({','.join('?' * len(scopes))}) ORDER BY created_at DESC LIMIT ?",  # noqa: S608
            (*scopes, limit),
        )
        return [self._fact(r) for r in rows]

    def search_facts(self, query: str, *, scopes: Iterable[str], limit: int = 10, include_candidates: bool = False) -> list[Fact]:
        scopes = list(scopes)
        terms = keyword_terms(query)
        if not scopes or not terms:
            return []
        statuses = ["confirmed", "candidate"] if include_candidates else ["confirmed"]
        for mode in ("AND", "OR"):
            match = fts_query(terms, mode=mode)
            try:
                rows = self.db.query(
                    f"""SELECT f.* FROM facts_fts JOIN facts f ON f.rowid = facts_fts.rowid
                        WHERE facts_fts MATCH ? AND f.scope IN ({','.join('?' * len(scopes))})
                          AND f.status IN ({','.join('?' * len(statuses))})
                        ORDER BY bm25(facts_fts), f.created_at DESC LIMIT ?""",  # noqa: S608
                    (match, *scopes, *statuses, limit),
                )
            except sqlite3.OperationalError as exc:
                raise ValidationFailed(f"fact query could not be parsed: {exc}") from exc
            if rows or len(terms) == 1:
                return [self._fact(r) for r in rows]
        return []

    def fact_history(self, fact_id: str, *, scopes: Iterable[str] | None = None) -> list[Fact]:
        f = self.get_fact(fact_id, scopes=scopes)
        root = f
        while root.supersedes_id:
            root = self.get_fact(root.supersedes_id)
        chain = [root]
        while chain[-1].superseded_by_id:
            chain.append(self.get_fact(chain[-1].superseded_by_id))
        return chain

    # ------------------------------------------------------------- projects
    def ensure_project(self, name: str, *, scope: str = "owner", description: str = "") -> dict[str, Any]:
        key = _key(name)
        row = self.db.query_one("SELECT * FROM projects WHERE name_key = ?", (key,))
        if row:
            return dict(row)
        now = self._now()
        pid = new_id("proj")
        self.db.execute(
            "INSERT INTO projects(id, name, name_key, description, status, scope, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (pid, name.strip(), key, description, "active", scope, now, now),
        )
        return dict(self.db.query_one("SELECT * FROM projects WHERE id = ?", (pid,)) or {})

    def list_projects(self, *, scopes: Iterable[str]) -> list[dict[str, Any]]:
        scopes = list(scopes)
        if not scopes:
            return []
        rows = self.db.query(f"SELECT * FROM projects WHERE scope IN ({','.join('?' * len(scopes))}) ORDER BY updated_at DESC", tuple(scopes))  # noqa: S608
        return [dict(r) for r in rows]

    def find_project(self, name: str) -> dict[str, Any] | None:
        key = _key(name)
        row = self.db.query_one("SELECT * FROM projects WHERE name_key = ?", (key,))
        if row:
            return dict(row)
        rows = self.db.query("SELECT * FROM projects WHERE name_key LIKE ?", (f"%{key}%",))
        return dict(rows[0]) if len(rows) == 1 else None

    # ------------------------------------------------------------ decisions
    def _decision(self, row: sqlite3.Row) -> Decision:
        d = {k: row[k] for k in Decision.model_fields if k in row.keys()}
        return Decision(**d)

    def record_decision(self, d: DecisionCreate, *, actor: str) -> Decision:
        now = self._now()
        project_id = self.ensure_project(d.project, scope=d.scope)["id"] if d.project else None
        did = new_id("dec")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO decisions(id, project_id, statement, rationale, status, scope, decided_at, stated_by,
                       source_document_id, source_chunk_id, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (did, project_id, d.statement.strip(), d.rationale, "current", d.scope, d.decided_at or now, actor,
                 d.source_document_id, d.source_chunk_id, now, now),
            )
            self._audit(conn, actor, "decision.record", did, project=d.project)
        return self.get_decision(did)

    def get_decision(self, decision_id: str, *, scopes: Iterable[str] | None = None) -> Decision:
        row = self.db.query_one(
            "SELECT d.*, p.name AS project_name FROM decisions d LEFT JOIN projects p ON p.id = d.project_id WHERE d.id = ?",
            (decision_id,),
        )
        if not row or (scopes is not None and row["scope"] not in set(scopes)):
            raise NotFound(f"decision {decision_id} not found")
        return self._decision(row)

    def supersede_decision(self, decision_id: str, new: DecisionCreate, *, actor: str, scopes: Iterable[str] | None = None) -> Decision:
        old = self.get_decision(decision_id, scopes=scopes)
        if old.status != "current":
            raise Conflict(f"decision is {old.status}; supersede the current one ({old.superseded_by_id})")
        if new.project is None and old.project_name:
            new = new.model_copy(update={"project": old.project_name})
        created = self.record_decision(new, actor=actor)
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute("UPDATE decisions SET status = 'superseded', superseded_by_id = ?, updated_at = ? WHERE id = ?", (created.id, now, old.id))
            conn.execute("UPDATE decisions SET supersedes_id = ? WHERE id = ?", (old.id, created.id))
            self._audit(conn, actor, "decision.supersede", old.id, new_id=created.id)
        return self.get_decision(created.id)

    def reverse_decision(self, decision_id: str, *, actor: str, reason: str = "", scopes: Iterable[str] | None = None) -> Decision:
        old = self.get_decision(decision_id, scopes=scopes)
        if old.status != "current":
            raise Conflict(f"decision is already {old.status}")
        now = self._now()
        with self.db.transaction() as conn:
            conn.execute("UPDATE decisions SET status = 'reversed', updated_at = ?, rationale = rationale || ? WHERE id = ?", (now, f"\n[reversed: {reason}]", decision_id))
            self._audit(conn, actor, "decision.reverse", decision_id, reason=reason)
        return self.get_decision(decision_id)

    def list_decisions(self, *, scopes: Iterable[str], project: str | None = None, include_history: bool = False, limit: int = 50) -> list[Decision]:
        scopes = list(scopes)
        if not scopes:
            return []
        sql = f"SELECT d.*, p.name AS project_name FROM decisions d LEFT JOIN projects p ON p.id = d.project_id WHERE d.scope IN ({','.join('?' * len(scopes))})"  # noqa: S608
        params: list[Any] = list(scopes)
        if project:
            proj = self.find_project(project)
            if not proj:
                return []
            sql += " AND d.project_id = ?"
            params.append(proj["id"])
        if not include_history:
            sql += " AND d.status = 'current'"
        sql += " ORDER BY d.decided_at DESC LIMIT ?"
        params.append(limit)
        return [self._decision(r) for r in self.db.query(sql, tuple(params))]

    def search_decisions(self, query: str, *, scopes: Iterable[str], limit: int = 10) -> list[Decision]:
        terms = keyword_terms(query)
        if not terms:
            return []
        scopes = list(scopes)
        like = [f"%{t}%" for t in terms]
        sql = (
            f"SELECT d.*, p.name AS project_name FROM decisions d LEFT JOIN projects p ON p.id = d.project_id "  # noqa: S608
            f"WHERE d.scope IN ({','.join('?' * len(scopes))}) AND d.status = 'current' AND ("
            + " OR ".join(["lower(d.statement) LIKE ?", "lower(COALESCE(p.name,'')) LIKE ?"] * len(like))
            + ") ORDER BY d.decided_at DESC LIMIT ?"
        )
        params: list[Any] = [*scopes]
        for pat in like:
            params += [pat, pat]
        params.append(limit)
        rows = self.db.query(sql, tuple(params))
        # rank by number of matched terms, newest first
        def score(r: sqlite3.Row) -> int:
            text = f"{r['statement']} {r['project_name'] or ''}".lower()
            return sum(1 for t in terms if t in text)
        ranked = sorted(rows, key=lambda r: (-score(r), r["decided_at"]), reverse=False)
        return [self._decision(r) for r in ranked]

    # -------------------------------------------------------------- actions
    def _action(self, row: sqlite3.Row) -> Action:
        return Action(**{k: row[k] for k in Action.model_fields})

    def create_action(self, a: ActionCreate, *, actor: str) -> Action:
        now = self._now()
        project_id = self.ensure_project(a.project, scope=a.scope)["id"] if a.project else None
        aid = new_id("act")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO actions(id, title, owner, owner_confidence, due_at, due_text, due_confidence, status, scope,
                       project_id, meeting_id, source_document_id, source_chunk_id, source_segment_id, source_quote,
                       created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (aid, a.title.strip(), a.owner, a.owner_confidence, a.due_at, a.due_text, a.due_confidence, a.status, a.scope,
                 project_id, a.meeting_id, a.source_document_id, a.source_chunk_id, a.source_segment_id, a.source_quote, now, now),
            )
            self._audit(conn, actor, "action.create", aid, status=a.status, meeting_id=a.meeting_id)
        return self.get_action(aid)

    def get_action(self, action_id: str, *, scopes: Iterable[str] | None = None) -> Action:
        row = self.db.query_one("SELECT * FROM actions WHERE id = ?", (action_id,))
        if not row or (scopes is not None and row["scope"] not in set(scopes)):
            raise NotFound(f"action {action_id} not found")
        return self._action(row)

    def update_action(self, action_id: str, *, actor: str, scopes: Iterable[str] | None = None, **fields: Any) -> Action:
        allowed = {"title", "owner", "owner_confidence", "due_at", "due_text", "due_confidence", "status"}
        bad = set(fields) - allowed
        if bad:
            raise ValidationFailed(f"cannot update {sorted(bad)}")
        a = self.get_action(action_id, scopes=scopes)
        now = self._now()
        sets = ", ".join(f"{k} = ?" for k in fields)
        params: list[Any] = list(fields.values())
        if fields.get("status") == "done" and a.status != "done":
            sets += ", completed_at = ?"
            params.append(now)
        sets += ", updated_at = ?"
        params += [now, action_id]
        with self.db.transaction() as conn:
            conn.execute(f"UPDATE actions SET {sets} WHERE id = ?", tuple(params))  # noqa: S608 - column names come from the allowlist above
            self._audit(conn, actor, "action.update", action_id, **{k: v for k, v in fields.items() if k != "title"})
        return self.get_action(action_id)

    def list_actions(self, *, scopes: Iterable[str], status: list[str] | None = None, meeting_id: str | None = None, limit: int = 100) -> list[Action]:
        scopes = list(scopes)
        if not scopes:
            return []
        sql = f"SELECT * FROM actions WHERE scope IN ({','.join('?' * len(scopes))})"  # noqa: S608
        params: list[Any] = list(scopes)
        if status:
            sql += f" AND status IN ({','.join('?' * len(status))})"
            params += status
        if meeting_id:
            sql += " AND meeting_id = ?"
            params.append(meeting_id)
        sql += " ORDER BY COALESCE(due_at, '9999') ASC, created_at DESC LIMIT ?"
        params.append(limit)
        return [self._action(r) for r in self.db.query(sql, tuple(params))]

    # ------------------------------------------------------------ purchases
    def _purchase(self, row: sqlite3.Row) -> Purchase:
        return Purchase(
            id=row["id"], merchant=row["merchant"], order_ref=row["order_ref"], items=json.loads(row["items_json"]),
            amount=row["amount"], currency=row["currency"], ordered_at=row["ordered_at"], status=row["status"],
            status_history=json.loads(row["status_history_json"]), scope=row["scope"],
            source_message_ids=json.loads(row["source_message_ids"]), source_document_id=row["source_document_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def upsert_purchase(self, p: PurchaseUpsert, *, actor: str) -> tuple[Purchase, str]:
        """Insert or merge an order update. Returns (purchase, 'created'|'updated'|'duplicate')."""
        now = self._now()
        mkey = _key(p.merchant)
        event = {"status": p.status, "at": p.event_at or now, "source_message_id": p.source_message_id}
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM purchases WHERE merchant_key = ? AND order_ref = ?", (mkey, p.order_ref.strip())).fetchone()
            if row is None:
                pid = new_id("pur")
                conn.execute(
                    """INSERT INTO purchases(id, merchant, merchant_key, order_ref, items_json, amount, currency, ordered_at, status,
                           status_history_json, scope, source_message_ids, source_document_id, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, p.merchant.strip(), mkey, p.order_ref.strip(), json.dumps(p.items), p.amount, p.currency, p.ordered_at, p.status,
                     json.dumps([event]), p.scope, json.dumps([p.source_message_id] if p.source_message_id else []), p.source_document_id, now, now),
                )
                self._audit(conn, actor, "purchase.create", pid, merchant=p.merchant, status=p.status)
                outcome = "created"
            else:
                srcs = json.loads(row["source_message_ids"])
                if p.source_message_id and p.source_message_id in srcs:
                    return self._purchase(row), "duplicate"
                history = json.loads(row["status_history_json"])
                history.append(event)
                current = row["status"]
                new_status = p.status if _PURCHASE_RANK[p.status] >= _PURCHASE_RANK[current] else current
                items = json.loads(row["items_json"]) or p.items
                if p.source_message_id:
                    srcs.append(p.source_message_id)
                conn.execute(
                    "UPDATE purchases SET status = ?, status_history_json = ?, items_json = ?, amount = COALESCE(?, amount), currency = COALESCE(?, currency),"
                    " ordered_at = COALESCE(ordered_at, ?), source_message_ids = ?, updated_at = ? WHERE id = ?",
                    (new_status, json.dumps(history), json.dumps(items), p.amount, p.currency, p.ordered_at, json.dumps(srcs), now, row["id"]),
                )
                self._audit(conn, actor, "purchase.update", row["id"], from_status=current, to_status=new_status)
                pid = row["id"]
                outcome = "updated"
        row = self.db.query_one("SELECT * FROM purchases WHERE id = ?", (pid,))
        assert row is not None
        return self._purchase(row), outcome

    def list_purchases(self, *, scopes: Iterable[str], merchant: str | None = None, since: str | None = None, limit: int = 100) -> list[Purchase]:
        scopes = list(scopes)
        if not scopes:
            return []
        sql = f"SELECT * FROM purchases WHERE scope IN ({','.join('?' * len(scopes))})"  # noqa: S608
        params: list[Any] = list(scopes)
        if merchant:
            sql += " AND merchant_key LIKE ?"
            params.append(f"%{_key(merchant)}%")
        if since:
            sql += " AND COALESCE(ordered_at, created_at) >= ?"
            params.append(since)
        sql += " ORDER BY COALESCE(ordered_at, created_at) DESC LIMIT ?"
        params.append(limit)
        return [self._purchase(r) for r in self.db.query(sql, tuple(params))]

    # ------------------------------------------------------- lesson progress
    def _progress(self, row: sqlite3.Row) -> LessonProgress:
        return LessonProgress(
            id=row["id"], course_id=row["course_id"], lesson_id=row["lesson_id"], status=row["status"], attempts=row["attempts"],
            correct=row["correct"], last_score=row["last_score"], weak_topics=json.loads(row["weak_topics_json"]),
            evidence=json.loads(row["evidence_json"]), updated_at=row["updated_at"],
        )

    def record_attempt(self, course_id: str, lesson_id: str, *, exercise_id: str, passed: bool, score: float | None, topics: list[str], actor: str, scope: str = "owner") -> LessonProgress:
        now = self._now()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM lesson_progress WHERE course_id = ? AND lesson_id = ?", (course_id, lesson_id)).fetchone()
            if row is None:
                pid = new_id("lp")
                conn.execute(
                    "INSERT INTO lesson_progress(id, course_id, lesson_id, status, attempts, correct, last_score, weak_topics_json, evidence_json, scope, created_at, updated_at)"
                    " VALUES (?,?,?,?,0,0,NULL,'[]','[]',?,?,?)",
                    (pid, course_id, lesson_id, "in_progress", scope, now, now),
                )
                row = conn.execute("SELECT * FROM lesson_progress WHERE id = ?", (pid,)).fetchone()
            evidence = json.loads(row["evidence_json"])
            evidence.append({"attempt_id": new_id("att"), "exercise_id": exercise_id, "passed": passed, "score": score, "at": now})
            weak = set(json.loads(row["weak_topics_json"]))
            if passed:
                weak -= set(topics)
            else:
                weak |= set(topics)
            attempts = row["attempts"] + 1
            correct = row["correct"] + (1 if passed else 0)
            recent = [e["passed"] for e in evidence[-3:]]
            if len(recent) >= 2 and all(recent[-2:]) and not weak:
                status = "mastered"
            elif not passed and attempts >= 2:
                status = "needs_review"
            else:
                status = "in_progress"
            conn.execute(
                "UPDATE lesson_progress SET status = ?, attempts = ?, correct = ?, last_score = ?, weak_topics_json = ?, evidence_json = ?, updated_at = ? WHERE id = ?",
                (status, attempts, correct, score, json.dumps(sorted(weak)), json.dumps(evidence), now, row["id"]),
            )
            self._audit(conn, actor, "lesson.attempt", row["id"], passed=passed, exercise=exercise_id)
            pid = row["id"]
        return self._progress(self.db.query_one("SELECT * FROM lesson_progress WHERE id = ?", (pid,)))  # type: ignore[arg-type]

    def progress(self, course_id: str, *, scopes: Iterable[str]) -> list[LessonProgress]:
        scopes = list(scopes)
        rows = self.db.query(
            f"SELECT * FROM lesson_progress WHERE course_id = ? AND scope IN ({','.join('?' * len(scopes))}) ORDER BY lesson_id",  # noqa: S608
            (course_id, *scopes),
        )
        return [self._progress(r) for r in rows]
