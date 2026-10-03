"""Conversation persistence (brain.db)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from companion_contracts.common import Source
from companion_contracts.conversation import Conversation, Message, Role
from companion_core.clock import Clock, SystemClock, iso
from companion_core.db import Database
from companion_core.errors import NotFound
from companion_core.ids import new_id

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class ConversationStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self.db = db
        self.clock = clock or SystemClock()

    def migrate(self) -> list[str]:
        return self.db.migrate(MIGRATIONS_DIR)

    def _now(self) -> str:
        return iso(self.clock.now())

    # -- conversations ---------------------------------------------------
    def create_conversation(self, client_id: str, title: str = "") -> Conversation:
        now = self._now()
        cid = new_id("conv")
        self.db.execute(
            "INSERT INTO conversations(id, client_id, title, state, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (cid, client_id, title, "active", now, now),
        )
        return Conversation(id=cid, client_id=client_id, title=title, state="active", created_at=now, updated_at=now)

    def get_conversation(self, conversation_id: str) -> Conversation:
        row = self.db.query_one(
            "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS n "
            "FROM conversations c WHERE id = ?",
            (conversation_id,),
        )
        if not row:
            raise NotFound(f"conversation {conversation_id} not found")
        return Conversation(
            id=row["id"], client_id=row["client_id"], title=row["title"], state=row["state"],
            created_at=row["created_at"], updated_at=row["updated_at"], message_count=row["n"],
        )

    def list_conversations(self, client_id: str, limit: int = 50) -> list[Conversation]:
        rows = self.db.query(
            "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS n "
            "FROM conversations c WHERE client_id = ? ORDER BY updated_at DESC LIMIT ?",
            (client_id, limit),
        )
        return [
            Conversation(
                id=r["id"], client_id=r["client_id"], title=r["title"], state=r["state"],
                created_at=r["created_at"], updated_at=r["updated_at"], message_count=r["n"],
            )
            for r in rows
        ]

    def set_title_if_empty(self, conversation_id: str, title: str) -> None:
        self.db.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND title = ''", (title[:120], conversation_id)
        )

    # -- messages --------------------------------------------------------
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        tool_name: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        sources: list[Source] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Message:
        now = self._now()
        mid = new_id("msg")
        role_t = cast(Role, role)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO messages(id, conversation_id, role, content, tool_name, tool_calls_json, sources_json, meta_json, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    mid, conversation_id, role, content, tool_name,
                    json.dumps(tool_calls or [], default=str),
                    json.dumps([s.model_dump(mode="json") for s in (sources or [])]),
                    json.dumps(meta or {}, default=str), now,
                ),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return Message(
            id=mid, conversation_id=conversation_id, role=role_t, content=content, tool_name=tool_name,
            tool_calls=tool_calls or [], sources=sources or [], meta=meta or {}, created_at=now,
        )

    def list_messages(self, conversation_id: str, limit: int = 500) -> list[Message]:
        rows = self.db.query(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid LIMIT ?",
            (conversation_id, limit),
        )
        return [
            Message(
                id=r["id"], conversation_id=r["conversation_id"], role=r["role"], content=r["content"],
                tool_name=r["tool_name"], tool_calls=json.loads(r["tool_calls_json"]),
                sources=[Source.model_validate(s) for s in json.loads(r["sources_json"])],
                meta=json.loads(r["meta_json"]), created_at=r["created_at"],
            )
            for r in rows
        ]

    def recent_turns(self, conversation_id: str, max_messages: int = 24) -> list[Message]:
        """Most recent user/assistant exchanges for the model context (tool traffic excluded)."""
        rows = self.db.query(
            "SELECT * FROM messages WHERE conversation_id = ? AND role IN ('user','assistant') "
            "AND json_extract(meta_json, '$.error') IS NULL ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (conversation_id, max_messages),
        )
        msgs = [
            Message(
                id=r["id"], conversation_id=r["conversation_id"], role=r["role"], content=r["content"],
                tool_name=r["tool_name"], tool_calls=json.loads(r["tool_calls_json"]),
                sources=[Source.model_validate(s) for s in json.loads(r["sources_json"])],
                meta=json.loads(r["meta_json"]), created_at=r["created_at"],
            )
            for r in rows
        ]
        msgs.reverse()
        return msgs

    # -- audit -----------------------------------------------------------
    def record_tool_invocation(
        self,
        *,
        conversation_id: str | None,
        client_id: str,
        call_id: str,
        tool_name: str,
        status: str,
        reason: str | None,
        args: Any,
        duration_ms: int | None,
        route: str,
    ) -> None:
        try:
            args_text = json.dumps(args, default=str)[:2000]
        except (TypeError, ValueError):
            args_text = "{}"
        self.db.execute(
            "INSERT INTO tool_invocations(at, conversation_id, client_id, call_id, tool_name, status, reason, args_json, duration_ms, route)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (self._now(), conversation_id, client_id, call_id, tool_name, status, reason, args_text, duration_ms, route),
        )

    def recent_tool_invocations(self, client_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM tool_invocations WHERE client_id = ? ORDER BY id DESC LIMIT ?", (client_id, limit)
        )
        return [dict(r) for r in rows]
