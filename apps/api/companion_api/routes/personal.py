"""Weather, maths, decks, email and orders endpoints for the desk UI."""

from __future__ import annotations

from typing import Annotated, Any

from companion_contracts.common import Provenance
from companion_contracts.vault import DocumentImport
from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import NotConfigured, NotFound, ValidationFailed
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require
from ..tools.gateway import ToolContext

router = APIRouter(prefix="/v1")


class MathsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=400)
    task: str = Field(default="evaluate", pattern=r"^(evaluate|simplify|solve|differentiate|integrate|explain)$")
    variable: str | None = Field(default=None, pattern=r"^[a-zA-Z]$")


class DeckImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    format: str = Field(min_length=2, max_length=30)
    commander: str | None = Field(default=None, max_length=120)
    decklist: str = Field(min_length=1, max_length=50000)
    notes: str = Field(default="", max_length=2000)


class DeckCheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card: str = Field(min_length=1, max_length=150)


class EmailSearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=50)
    page_token: str | None = None


async def _tool(request: Request, identity: ClientIdentity, name: str, args: dict[str, Any]) -> dict[str, Any]:
    st = request.app.state.companion
    outcome = await st.gateway.call(ToolContext(identity=identity, state=st, route="ui"), f"ui_{name}", name, args)
    if outcome.result is None:
        from companion_core.errors import PermissionDenied

        raise PermissionDenied(outcome.call_event.reason or "denied")
    import json

    if not outcome.result.ok:
        from companion_core.errors import CompanionError, NotFound, UpstreamUnavailable

        mapping: dict[str, type[CompanionError]] = {"validation_failed": ValidationFailed, "not_found": NotFound, "not_configured": NotConfigured, "timeout": UpstreamUnavailable, "upstream_unavailable": UpstreamUnavailable}
        exc_cls = mapping.get(outcome.result.error_code or "", CompanionError)
        raise exc_cls(outcome.result.summary or "tool failed")
    return {"ok": outcome.result.ok, "summary": outcome.result.summary, "data": json.loads(outcome.result.content), "sources": [s.model_dump() for s in outcome.result.sources]}


@router.get("/weather")
async def weather(identity: Annotated[ClientIdentity, Depends(require(Permission.WEATHER_READ))], request: Request, day: str = "week"):
    if day not in {"today", "tomorrow", "week"}:
        raise ValidationFailed("day must be today, tomorrow or week")
    return await _tool(request, identity, "weather_forecast", {"day": day})


@router.post("/maths")
async def maths(body: MathsBody, identity: Annotated[ClientIdentity, Depends(require(Permission.MATHS_USE))], request: Request):
    return await _tool(request, identity, "maths", body.model_dump(exclude_none=True))


Decker = Annotated[ClientIdentity, Depends(require(Permission.MTG_READ))]


@router.post("/mtg/decks", status_code=201)
async def import_deck(body: DeckImport, identity: Annotated[ClientIdentity, Depends(require(Permission.MEMORY_WRITE))], request: Request):
    from companion_integrations.mtg.base import FORMATS
    from companion_integrations.mtg.decks import deck_summary, parse_decklist

    if body.format.lower() not in FORMATS:
        raise ValidationFailed(f"unknown format {body.format!r}; known: {', '.join(FORMATS[:8])} ...")
    deck = parse_decklist(body.decklist, name=body.name, format=body.format, commander=body.commander)
    deck.notes = body.notes
    st = request.app.state.companion
    doc = await st.vault.import_document(
        DocumentImport(title=deck.name, text=body.decklist, kind="deck", provenance=Provenance(source_type="manual", source_ref=f"deck:{deck.name}", captured_by=identity.client_id, trust="owner_stated"),
                       metadata={"type": "mtg_deck", "deck": deck.model_dump(), "summary": deck_summary(deck)}, idempotency_key=f"deck:{identity.client_id}:{deck.name.lower()}:{hash(body.decklist) & 0xFFFFFFFF}"),
        actor=identity.client_id,
    )
    return {"document_id": doc.id, "deck": deck.model_dump(), "summary": deck_summary(deck)}


@router.get("/mtg/decks")
async def list_decks(identity: Decker, request: Request):
    st = request.app.state.companion
    docs = await st.vault.list_documents(scopes=identity.memory_scopes, kinds=["deck"], limit=100)
    return [{"document_id": d.id, "name": d.title, **(d.metadata.get("summary") or {}), "created_at": d.created_at} for d in docs]


@router.get("/mtg/decks/{document_id}")
async def get_deck(document_id: str, identity: Decker, request: Request):
    st = request.app.state.companion
    d = await st.vault.get_document(document_id, scopes=identity.memory_scopes)
    if d.kind != "deck":
        raise NotFound("not a deck")
    return {"document_id": d.id, "deck": d.metadata["deck"], "decklist": d.text, "summary": d.metadata.get("summary")}


@router.post("/mtg/decks/{document_id}/check")
async def check_deck_card(document_id: str, body: DeckCheckBody, identity: Decker, request: Request):
    st = request.app.state.companion
    d = await st.vault.get_document(document_id, scopes=identity.memory_scopes)
    return await _tool(request, identity, "deck_card_check", {"deck": d.title, "card": body.card})


@router.get("/email/status")
async def email_status(identity: Annotated[ClientIdentity, Depends(require(Permission.EMAIL_READ))], request: Request):
    st = request.app.state.companion
    if st.email is None:
        return {"enabled": False, "provider": None}
    return {"enabled": True, "provider": st.email.name, "is_fixture": st.email.is_fixture, "account": st.email.account_label, "health": (await st.email.health()).model_dump(), "read_only": True}


@router.post("/email/search")
async def email_search(body: EmailSearchBody, identity: Annotated[ClientIdentity, Depends(require(Permission.EMAIL_READ))], request: Request):
    st = request.app.state.companion
    if st.email is None:
        raise NotConfigured("email.provider is disabled")
    from companion_integrations.orders.extract import redact_payment

    res = await st.email.search(body.query, limit=body.limit, page_token=body.page_token)
    return {"query": res.query, "provider": res.provider, "is_fixture": res.is_fixture, "next_page_token": res.next_page_token,
            "messages": [{**m.model_dump(exclude={"body_text"}), "snippet": redact_payment(m.snippet), "body_excerpt": redact_payment(m.body_text)[:800]} for m in res.messages]}


@router.get("/orders")
async def orders(identity: Annotated[ClientIdentity, Depends(require(Permission.EMAIL_READ))], request: Request, merchant: str | None = None, days: int = 90, sync: bool = False):
    if sync:
        return await _tool(request, identity, "orders_search", {"merchant": merchant, "days": days})
    st = request.app.state.companion
    import datetime as dt

    since = (st.clock.now() - dt.timedelta(days=days)).isoformat()
    return [p.model_dump() for p in await st.vault.list_purchases(scopes=identity.memory_scopes, merchant=merchant, since=since)]


@router.delete("/orders/fixtures")
async def delete_fixture_orders(identity: Annotated[ClientIdentity, Depends(require(Permission.MEMORY_WRITE))], request: Request):
    """Remove purchases that came only from the fixture (demo) mailbox. Live purchases stay."""
    st = request.app.state.companion
    deleted = await st.vault.delete_fixture_purchases(actor=identity.client_id, scopes=identity.memory_scopes)
    return {"deleted": deleted, "note": "only fixture-sourced purchases were removed"}
