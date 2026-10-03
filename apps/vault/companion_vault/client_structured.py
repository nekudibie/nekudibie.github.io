"""Structured-memory methods shared by the local and HTTP vault clients.

Split from client.py so both client classes can inherit them (facts, decisions, actions,
purchases, lesson progress) while orchestration code stays location-agnostic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from .structured import (
    Action,
    ActionCreate,
    Decision,
    DecisionCreate,
    Fact,
    FactCreate,
    LessonProgress,
    Purchase,
    PurchaseUpsert,
)

if TYPE_CHECKING:
    from .service import VaultService


class _StructuredLocal:
    """Mixin for LocalVaultClient."""

    service: VaultService

    def _s(self) -> Any:
        return self.service.structured

    async def add_fact(self, f: FactCreate, *, actor: str) -> Fact:
        return await asyncio.to_thread(self._s().add_fact, f, actor=actor)

    async def list_facts(self, *, scopes: Iterable[str], subject: str | None = None, predicate: str | None = None, include_candidates: bool = False) -> list[Fact]:
        return await asyncio.to_thread(self._s().current_facts, scopes=list(scopes), subject=subject, predicate=predicate, include_candidates=include_candidates)

    async def search_facts(self, query: str, *, scopes: Iterable[str], limit: int = 10, include_candidates: bool = False) -> list[Fact]:
        return await asyncio.to_thread(self._s().search_facts, query, scopes=list(scopes), limit=limit, include_candidates=include_candidates)

    async def candidates(self, *, scopes: Iterable[str], limit: int = 50) -> list[Fact]:
        return await asyncio.to_thread(self._s().candidates, scopes=list(scopes), limit=limit)

    async def confirm_fact(self, fact_id: str, *, actor: str, scopes: Iterable[str]) -> Fact:
        return await asyncio.to_thread(self._s().confirm_fact, fact_id, actor=actor, scopes=list(scopes))

    async def reject_fact(self, fact_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Fact:
        return await asyncio.to_thread(self._s().reject_fact, fact_id, actor=actor, reason=reason, scopes=list(scopes))

    async def retract_fact(self, fact_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Fact:
        return await asyncio.to_thread(self._s().retract_fact, fact_id, actor=actor, reason=reason, scopes=list(scopes))

    async def update_fact(self, fact_id: str, new_value: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Fact:
        return await asyncio.to_thread(self._s().update_fact, fact_id, new_value, actor=actor, reason=reason, scopes=list(scopes))

    async def fact_history(self, fact_id: str, *, scopes: Iterable[str]) -> list[Fact]:
        return await asyncio.to_thread(self._s().fact_history, fact_id, scopes=list(scopes))

    async def record_decision(self, d: DecisionCreate, *, actor: str) -> Decision:
        return await asyncio.to_thread(self._s().record_decision, d, actor=actor)

    async def list_decisions(self, *, scopes: Iterable[str], project: str | None = None, include_history: bool = False) -> list[Decision]:
        return await asyncio.to_thread(self._s().list_decisions, scopes=list(scopes), project=project, include_history=include_history)

    async def search_decisions(self, query: str, *, scopes: Iterable[str], limit: int = 10) -> list[Decision]:
        return await asyncio.to_thread(self._s().search_decisions, query, scopes=list(scopes), limit=limit)

    async def supersede_decision(self, decision_id: str, new: DecisionCreate, *, actor: str, scopes: Iterable[str]) -> Decision:
        return await asyncio.to_thread(self._s().supersede_decision, decision_id, new, actor=actor, scopes=list(scopes))

    async def reverse_decision(self, decision_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Decision:
        return await asyncio.to_thread(self._s().reverse_decision, decision_id, actor=actor, reason=reason, scopes=list(scopes))

    async def create_action(self, a: ActionCreate, *, actor: str) -> Action:
        return await asyncio.to_thread(self._s().create_action, a, actor=actor)

    async def list_actions(self, *, scopes: Iterable[str], status: list[str] | None = None, meeting_id: str | None = None) -> list[Action]:
        return await asyncio.to_thread(self._s().list_actions, scopes=list(scopes), status=status, meeting_id=meeting_id)

    async def update_action(self, action_id: str, fields: dict[str, Any], *, actor: str, scopes: Iterable[str]) -> Action:
        return await asyncio.to_thread(lambda: self._s().update_action(action_id, actor=actor, scopes=list(scopes), **fields))

    async def upsert_purchase(self, p: PurchaseUpsert, *, actor: str) -> tuple[Purchase, str]:
        return await asyncio.to_thread(self._s().upsert_purchase, p, actor=actor)

    async def list_purchases(self, *, scopes: Iterable[str], merchant: str | None = None, since: str | None = None) -> list[Purchase]:
        return await asyncio.to_thread(self._s().list_purchases, scopes=list(scopes), merchant=merchant, since=since)

    async def record_attempt(self, course_id: str, lesson_id: str, *, exercise_id: str, passed: bool, score: float | None, topics: list[str], actor: str) -> LessonProgress:
        return await asyncio.to_thread(self._s().record_attempt, course_id, lesson_id, exercise_id=exercise_id, passed=passed, score=score, topics=topics, actor=actor)

    async def progress(self, course_id: str, *, scopes: Iterable[str]) -> list[LessonProgress]:
        return await asyncio.to_thread(self._s().progress, course_id, scopes=list(scopes))


class _StructuredHttp:
    """Mixin for HttpVaultClient."""

    async def _req(self, method: str, path: str, *, actor: str | None = None, scopes: Iterable[str] | None = None, **kw: Any) -> Any: ...  # provided by HttpVaultClient

    async def add_fact(self, f: FactCreate, *, actor: str) -> Fact:
        return Fact.model_validate(await self._req("POST", "/v1/vault/facts", actor=actor, json=f.model_dump(mode="json")))

    async def list_facts(self, *, scopes: Iterable[str], subject: str | None = None, predicate: str | None = None, include_candidates: bool = False) -> list[Fact]:
        params = {k: v for k, v in {"subject": subject, "predicate": predicate, "include_candidates": include_candidates}.items() if v not in (None, False)}
        return [Fact.model_validate(x) for x in await self._req("GET", "/v1/vault/facts", scopes=scopes, params=params)]

    async def search_facts(self, query: str, *, scopes: Iterable[str], limit: int = 10, include_candidates: bool = False) -> list[Fact]:
        return [Fact.model_validate(x) for x in await self._req("POST", "/v1/vault/facts/search", scopes=scopes, json={"query": query, "limit": limit, "include_candidates": include_candidates})]

    async def candidates(self, *, scopes: Iterable[str], limit: int = 50) -> list[Fact]:
        return [Fact.model_validate(x) for x in await self._req("GET", "/v1/vault/facts/candidates", scopes=scopes, params={"limit": limit})]

    async def confirm_fact(self, fact_id: str, *, actor: str, scopes: Iterable[str]) -> Fact:
        return Fact.model_validate(await self._req("POST", f"/v1/vault/facts/{fact_id}/confirm", actor=actor, scopes=scopes))

    async def reject_fact(self, fact_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Fact:
        return Fact.model_validate(await self._req("POST", f"/v1/vault/facts/{fact_id}/reject", actor=actor, scopes=scopes, json={"reason": reason}))

    async def retract_fact(self, fact_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Fact:
        return Fact.model_validate(await self._req("POST", f"/v1/vault/facts/{fact_id}/retract", actor=actor, scopes=scopes, json={"reason": reason}))

    async def update_fact(self, fact_id: str, new_value: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Fact:
        return Fact.model_validate(await self._req("POST", f"/v1/vault/facts/{fact_id}/update", actor=actor, scopes=scopes, json={"value": new_value, "reason": reason}))

    async def fact_history(self, fact_id: str, *, scopes: Iterable[str]) -> list[Fact]:
        return [Fact.model_validate(x) for x in await self._req("GET", f"/v1/vault/facts/{fact_id}/history", scopes=scopes)]

    async def record_decision(self, d: DecisionCreate, *, actor: str) -> Decision:
        return Decision.model_validate(await self._req("POST", "/v1/vault/decisions", actor=actor, json=d.model_dump(mode="json")))

    async def list_decisions(self, *, scopes: Iterable[str], project: str | None = None, include_history: bool = False) -> list[Decision]:
        params = {k: v for k, v in {"project": project, "include_history": include_history}.items() if v not in (None, False)}
        return [Decision.model_validate(x) for x in await self._req("GET", "/v1/vault/decisions", scopes=scopes, params=params)]

    async def search_decisions(self, query: str, *, scopes: Iterable[str], limit: int = 10) -> list[Decision]:
        return [Decision.model_validate(x) for x in await self._req("POST", "/v1/vault/decisions/search", scopes=scopes, json={"query": query, "limit": limit})]

    async def supersede_decision(self, decision_id: str, new: DecisionCreate, *, actor: str, scopes: Iterable[str]) -> Decision:
        return Decision.model_validate(await self._req("POST", f"/v1/vault/decisions/{decision_id}/supersede", actor=actor, scopes=scopes, json=new.model_dump(mode="json")))

    async def reverse_decision(self, decision_id: str, *, actor: str, scopes: Iterable[str], reason: str = "") -> Decision:
        return Decision.model_validate(await self._req("POST", f"/v1/vault/decisions/{decision_id}/reverse", actor=actor, scopes=scopes, json={"reason": reason}))

    async def create_action(self, a: ActionCreate, *, actor: str) -> Action:
        return Action.model_validate(await self._req("POST", "/v1/vault/actions", actor=actor, json=a.model_dump(mode="json")))

    async def list_actions(self, *, scopes: Iterable[str], status: list[str] | None = None, meeting_id: str | None = None) -> list[Action]:
        params: list[tuple[str, Any]] = [("status", s) for s in (status or [])]
        if meeting_id:
            params.append(("meeting_id", meeting_id))
        return [Action.model_validate(x) for x in await self._req("GET", "/v1/vault/actions", scopes=scopes, params=params)]

    async def update_action(self, action_id: str, fields: dict[str, Any], *, actor: str, scopes: Iterable[str]) -> Action:
        return Action.model_validate(await self._req("PATCH", f"/v1/vault/actions/{action_id}", actor=actor, scopes=scopes, json=fields))

    async def upsert_purchase(self, p: PurchaseUpsert, *, actor: str) -> tuple[Purchase, str]:
        data = await self._req("POST", "/v1/vault/purchases", actor=actor, json=p.model_dump(mode="json"))
        return Purchase.model_validate(data["purchase"]), data["outcome"]

    async def list_purchases(self, *, scopes: Iterable[str], merchant: str | None = None, since: str | None = None) -> list[Purchase]:
        params = {k: v for k, v in {"merchant": merchant, "since": since}.items() if v}
        return [Purchase.model_validate(x) for x in await self._req("GET", "/v1/vault/purchases", scopes=scopes, params=params)]

    async def record_attempt(self, course_id: str, lesson_id: str, *, exercise_id: str, passed: bool, score: float | None, topics: list[str], actor: str) -> LessonProgress:
        return LessonProgress.model_validate(await self._req("POST", f"/v1/vault/lessons/{course_id}/{lesson_id}/attempts", actor=actor, json={"exercise_id": exercise_id, "passed": passed, "score": score, "topics": topics}))

    async def progress(self, course_id: str, *, scopes: Iterable[str]) -> list[LessonProgress]:
        return [LessonProgress.model_validate(x) for x in await self._req("GET", f"/v1/vault/lessons/{course_id}", scopes=scopes)]


