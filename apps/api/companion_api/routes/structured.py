"""Structured memory endpoints for the desk UI: facts (with candidate review), decisions, actions, purchases."""

from __future__ import annotations

from typing import Annotated, Any

from companion_core.auth import ClientIdentity, Permission
from companion_vault.structured import ActionCreate, DecisionCreate, FactCreate
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from ..auth import require

router = APIRouter(prefix="/v1/memory")
Reader = Annotated[ClientIdentity, Depends(require(Permission.MEMORY_READ))]
Writer = Annotated[ClientIdentity, Depends(require(Permission.MEMORY_WRITE))]


class Reason(BaseModel):
    reason: str = Field(default="", max_length=500)


class FactUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=2000)
    reason: str = Field(default="", max_length=500)


def _v(request: Request) -> Any:
    return request.app.state.companion.vault


@router.get("/facts")
async def list_facts(identity: Reader, request: Request, subject: str | None = None, predicate: str | None = None, include_candidates: bool = False):
    return await _v(request).list_facts(scopes=identity.memory_scopes, subject=subject, predicate=predicate, include_candidates=include_candidates)


@router.post("/facts", status_code=201)
async def add_fact(f: FactCreate, identity: Writer, request: Request):
    if f.scope not in identity.memory_scopes:
        f = f.model_copy(update={"scope": "owner" if "owner" in identity.memory_scopes else sorted(identity.memory_scopes)[0]})
    return await _v(request).add_fact(f, actor=identity.client_id)


@router.get("/facts/candidates")
async def candidates(identity: Reader, request: Request, limit: int = 50):
    return await _v(request).candidates(scopes=identity.memory_scopes, limit=limit)


@router.post("/facts/{fact_id}/confirm")
async def confirm(fact_id: str, identity: Writer, request: Request):
    return await _v(request).confirm_fact(fact_id, actor=identity.client_id, scopes=identity.memory_scopes)


@router.post("/facts/{fact_id}/reject")
async def reject(fact_id: str, body: Reason, identity: Writer, request: Request):
    return await _v(request).reject_fact(fact_id, actor=identity.client_id, scopes=identity.memory_scopes, reason=body.reason)


@router.post("/facts/{fact_id}/retract")
async def retract(fact_id: str, body: Reason, identity: Writer, request: Request):
    return await _v(request).retract_fact(fact_id, actor=identity.client_id, scopes=identity.memory_scopes, reason=body.reason)


@router.post("/facts/{fact_id}/update")
async def update(fact_id: str, body: FactUpdate, identity: Writer, request: Request):
    return await _v(request).update_fact(fact_id, body.value, actor=identity.client_id, scopes=identity.memory_scopes, reason=body.reason)


@router.get("/facts/{fact_id}/history")
async def fact_history(fact_id: str, identity: Reader, request: Request):
    return await _v(request).fact_history(fact_id, scopes=identity.memory_scopes)


@router.get("/decisions")
async def list_decisions(identity: Reader, request: Request, project: str | None = None, include_history: bool = False):
    return await _v(request).list_decisions(scopes=identity.memory_scopes, project=project, include_history=include_history)


@router.post("/decisions", status_code=201)
async def record_decision(d: DecisionCreate, identity: Writer, request: Request):
    return await _v(request).record_decision(d, actor=identity.client_id)


@router.post("/decisions/{decision_id}/supersede")
async def supersede(decision_id: str, d: DecisionCreate, identity: Writer, request: Request):
    return await _v(request).supersede_decision(decision_id, d, actor=identity.client_id, scopes=identity.memory_scopes)


@router.post("/decisions/{decision_id}/reverse")
async def reverse(decision_id: str, body: Reason, identity: Writer, request: Request):
    return await _v(request).reverse_decision(decision_id, actor=identity.client_id, scopes=identity.memory_scopes, reason=body.reason)


@router.get("/actions")
async def list_actions(identity: Reader, request: Request, status: Annotated[list[str] | None, Query()] = None, meeting_id: str | None = None):
    return await _v(request).list_actions(scopes=identity.memory_scopes, status=status, meeting_id=meeting_id)


@router.post("/actions", status_code=201)
async def create_action(a: ActionCreate, identity: Writer, request: Request):
    return await _v(request).create_action(a, actor=identity.client_id)


@router.patch("/actions/{action_id}")
async def update_action(action_id: str, fields: dict[str, Any], identity: Writer, request: Request):
    return await _v(request).update_action(action_id, fields, actor=identity.client_id, scopes=identity.memory_scopes)


@router.get("/purchases")
async def list_purchases(identity: Reader, request: Request, merchant: str | None = None, since: str | None = None):
    return await _v(request).list_purchases(scopes=identity.memory_scopes, merchant=merchant, since=since)
