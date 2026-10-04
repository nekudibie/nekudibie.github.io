"""Vault HTTP service (used when ``vault.mode: remote``).

Authentication: a single service bearer token (``vault.token_env``). The calling
API forwards the acting client id and its memory scopes in headers so the vault
can enforce scope and keep an audit trail per actor.
"""

# NOTE: no `from __future__ import annotations` here: the ActorDep alias is closure-local and
# FastAPI must see real Annotated objects, not strings, to register the dependency.
import hmac
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from companion_contracts.health import DependencyStatus, Readiness
from companion_contracts.vault import (
    CorrectionRequest,
    DeleteResponse,
    Document,
    DocumentImport,
    NoteCreate,
    SearchRequest,
    SearchResponse,
)
from companion_core.auth import hash_token
from companion_core.clock import iso, now_utc
from companion_core.config import AppConfig
from companion_core.db import Database
from companion_core.errors import CompanionError
from companion_core.ids import new_id
from companion_core.logging import get_logger, request_id_var
from companion_core.version import version_info
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .service import VaultService
from .structured import ActionCreate, DecisionCreate, FactCreate, PurchaseUpsert


class _Reason(BaseModel):
    reason: str = ""


class _FactUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=2000)
    reason: str = ""


class _FactSearch(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    include_candidates: bool = False


class _DecisionSearch(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)


class _Attempt(BaseModel):
    exercise_id: str
    passed: bool
    score: float | None = None
    topics: list[str] = Field(default_factory=list)

log = get_logger(__name__)


def build_service(cfg: AppConfig) -> VaultService:
    db = Database(cfg.vault_db_path)
    svc = VaultService(db, chunk_chars=cfg.vault.chunk_chars, chunk_overlap_chars=cfg.vault.chunk_overlap_chars)
    svc.migrate()
    return svc


class Actor:
    def __init__(self, client_id: str, scopes: list[str]) -> None:
        self.client_id = client_id
        self.scopes = scopes


def create_app(cfg: AppConfig, service: VaultService | None = None) -> FastAPI:
    token = cfg.vault_service_token()
    expected = hash_token(token) if token else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service or build_service(cfg)
        log.info("vault ready", extra={"db": str(cfg.vault_db_path)})
        yield
        app.state.service.db.close()

    app = FastAPI(title="Companion Vault", version=version_info("vault")["version"] or "0", lifespan=lifespan)
    if service is not None:
        app.state.service = service

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_id("req")
        token_ = request_id_var.set(rid)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_var.reset(token_)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(CompanionError)
    async def _companion_error(_: Request, exc: CompanionError):
        return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})

    def require_actor(
        authorization: Annotated[str | None, Header()] = None,
        x_companion_actor: Annotated[str | None, Header()] = None,
        x_companion_scopes: Annotated[str | None, Header()] = None,
    ) -> Actor:
        if expected is None:
            raise HTTPException(status_code=503, detail="vault service token not configured (vault.token_env)")
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        presented = authorization.split(" ", 1)[1].strip()
        if not hmac.compare_digest(hash_token(presented), expected):
            raise HTTPException(status_code=401, detail="invalid token")
        scopes = [s for s in (x_companion_scopes or "owner,shared").split(",") if s]
        return Actor(x_companion_actor or "api", scopes)

    ActorDep = Annotated[Actor, Depends(require_actor)]

    def svc(request: Request) -> VaultService:
        return request.app.state.service

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "service": "vault"}

    @app.get("/readyz", response_model=Readiness)
    async def readyz(request: Request):
        s = svc(request)
        ok = s.db.integrity_ok()
        return Readiness(
            ready=ok,
            service="vault",
            dependencies=[DependencyStatus(name="sqlite", status="ok" if ok else "down", detail=s.db.schema_version() or "")],
            checked_at=iso(now_utc()),
        )

    @app.get("/version")
    async def version():
        return version_info("vault")

    @app.post("/v1/vault/notes", response_model=Document, status_code=201)
    async def create_note(note: NoteCreate, actor: ActorDep, request: Request):
        return svc(request).create_note(note, actor=actor.client_id)

    @app.post("/v1/vault/documents", response_model=Document, status_code=201)
    async def import_document(imp: DocumentImport, actor: ActorDep, request: Request):
        return svc(request).import_document(imp, actor=actor.client_id)

    @app.get("/v1/vault/documents", response_model=list[Document])
    async def list_documents(
        actor: ActorDep,
        request: Request,
        kind: Annotated[list[str] | None, Query()] = None,
        project: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_superseded: bool = False,
    ):
        return svc(request).list_documents(
            scopes=actor.scopes, kinds=kind, project=project, limit=limit, offset=offset,
            include_superseded=include_superseded,
        )

    @app.get("/v1/vault/documents/{document_id}", response_model=Document)
    async def get_document(document_id: str, actor: ActorDep, request: Request):
        return svc(request).get_document(document_id, scopes=actor.scopes)

    @app.get("/v1/vault/documents/{document_id}/history", response_model=list[Document])
    async def history(document_id: str, actor: ActorDep, request: Request):
        return svc(request).history(document_id, scopes=actor.scopes)

    @app.post("/v1/vault/documents/{document_id}/correct", response_model=Document)
    async def correct(document_id: str, req: CorrectionRequest, actor: ActorDep, request: Request):
        return svc(request).correct(document_id, req, actor=actor.client_id, scopes=actor.scopes)

    @app.delete("/v1/vault/documents/{document_id}", response_model=DeleteResponse)
    async def delete(document_id: str, actor: ActorDep, request: Request, reason: str = ""):
        return svc(request).delete(document_id, actor=actor.client_id, scopes=actor.scopes, reason=reason)

    @app.get("/v1/vault/chunks/{chunk_id}")
    async def get_chunk(chunk_id: str, actor: ActorDep, request: Request):
        return svc(request).get_chunk(chunk_id, scopes=actor.scopes)

    @app.post("/v1/vault/search", response_model=SearchResponse)
    async def search(req: SearchRequest, actor: ActorDep, request: Request):
        return svc(request).search(req, scopes=actor.scopes)

    @app.get("/v1/vault/stats")
    async def stats(actor: ActorDep, request: Request):
        return svc(request).stats()

    @app.get("/v1/vault/export")
    async def export(actor: ActorDep, request: Request, include_deleted: bool = False):
        def gen() -> Iterator[str]:
            yield from svc(request).export_jsonl(scopes=actor.scopes, include_deleted=include_deleted)

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    sm = lambda request: svc(request).structured  # noqa: E731

    @app.post("/v1/vault/facts", status_code=201)
    async def add_fact(f: FactCreate, actor: ActorDep, request: Request):
        return sm(request).add_fact(f, actor=actor.client_id)

    @app.get("/v1/vault/facts")
    async def list_facts(actor: ActorDep, request: Request, subject: str | None = None, predicate: str | None = None, include_candidates: bool = False):
        return sm(request).current_facts(scopes=actor.scopes, subject=subject, predicate=predicate, include_candidates=include_candidates)

    @app.post("/v1/vault/facts/search")
    async def search_facts(req: _FactSearch, actor: ActorDep, request: Request):
        return sm(request).search_facts(req.query, scopes=actor.scopes, limit=req.limit, include_candidates=req.include_candidates)

    @app.get("/v1/vault/facts/candidates")
    async def candidates(actor: ActorDep, request: Request, limit: int = 50):
        return sm(request).candidates(scopes=actor.scopes, limit=limit)

    @app.post("/v1/vault/facts/{fact_id}/confirm")
    async def confirm_fact(fact_id: str, actor: ActorDep, request: Request):
        return sm(request).confirm_fact(fact_id, actor=actor.client_id, scopes=actor.scopes)

    @app.post("/v1/vault/facts/{fact_id}/reject")
    async def reject_fact(fact_id: str, body: _Reason, actor: ActorDep, request: Request):
        return sm(request).reject_fact(fact_id, actor=actor.client_id, reason=body.reason, scopes=actor.scopes)

    @app.post("/v1/vault/facts/{fact_id}/retract")
    async def retract_fact(fact_id: str, body: _Reason, actor: ActorDep, request: Request):
        return sm(request).retract_fact(fact_id, actor=actor.client_id, reason=body.reason, scopes=actor.scopes)

    @app.post("/v1/vault/facts/{fact_id}/update")
    async def update_fact(fact_id: str, body: _FactUpdate, actor: ActorDep, request: Request):
        return sm(request).update_fact(fact_id, body.value, actor=actor.client_id, reason=body.reason, scopes=actor.scopes)

    @app.get("/v1/vault/facts/{fact_id}/history")
    async def fact_history(fact_id: str, actor: ActorDep, request: Request):
        return sm(request).fact_history(fact_id, scopes=actor.scopes)

    @app.post("/v1/vault/decisions", status_code=201)
    async def record_decision(d: DecisionCreate, actor: ActorDep, request: Request):
        return sm(request).record_decision(d, actor=actor.client_id)

    @app.get("/v1/vault/decisions")
    async def list_decisions(actor: ActorDep, request: Request, project: str | None = None, include_history: bool = False):
        return sm(request).list_decisions(scopes=actor.scopes, project=project, include_history=include_history)

    @app.post("/v1/vault/decisions/search")
    async def search_decisions(req: _DecisionSearch, actor: ActorDep, request: Request):
        return sm(request).search_decisions(req.query, scopes=actor.scopes, limit=req.limit)

    @app.post("/v1/vault/decisions/{decision_id}/supersede")
    async def supersede_decision(decision_id: str, d: DecisionCreate, actor: ActorDep, request: Request):
        return sm(request).supersede_decision(decision_id, d, actor=actor.client_id, scopes=actor.scopes)

    @app.post("/v1/vault/decisions/{decision_id}/reverse")
    async def reverse_decision(decision_id: str, body: _Reason, actor: ActorDep, request: Request):
        return sm(request).reverse_decision(decision_id, actor=actor.client_id, reason=body.reason, scopes=actor.scopes)

    @app.post("/v1/vault/actions", status_code=201)
    async def create_action(a: ActionCreate, actor: ActorDep, request: Request):
        return sm(request).create_action(a, actor=actor.client_id)

    @app.get("/v1/vault/actions")
    async def list_actions(actor: ActorDep, request: Request, status: Annotated[list[str] | None, Query()] = None, meeting_id: str | None = None):
        return sm(request).list_actions(scopes=actor.scopes, status=status, meeting_id=meeting_id)

    @app.patch("/v1/vault/actions/{action_id}")
    async def update_action(action_id: str, fields: dict, actor: ActorDep, request: Request):
        return sm(request).update_action(action_id, actor=actor.client_id, scopes=actor.scopes, **fields)

    @app.post("/v1/vault/purchases")
    async def upsert_purchase(p: PurchaseUpsert, actor: ActorDep, request: Request):
        purchase, outcome = sm(request).upsert_purchase(p, actor=actor.client_id)
        return {"purchase": purchase, "outcome": outcome}

    @app.get("/v1/vault/purchases")
    async def list_purchases(actor: ActorDep, request: Request, merchant: str | None = None, since: str | None = None):
        return sm(request).list_purchases(scopes=actor.scopes, merchant=merchant, since=since)

    @app.delete("/v1/vault/purchases/fixtures")
    async def delete_fixture_purchases(actor: ActorDep, request: Request):
        return {"deleted": sm(request).delete_fixture_purchases(actor=actor.client_id, scopes=actor.scopes)}

    @app.post("/v1/vault/lessons/{course_id}/{lesson_id}/attempts")
    async def record_attempt(course_id: str, lesson_id: str, body: _Attempt, actor: ActorDep, request: Request):
        return sm(request).record_attempt(course_id, lesson_id, exercise_id=body.exercise_id, passed=body.passed, score=body.score, topics=body.topics, actor=actor.client_id)

    @app.get("/v1/vault/lessons/{course_id}")
    async def progress(course_id: str, actor: ActorDep, request: Request):
        return sm(request).progress(course_id, scopes=actor.scopes)

    @app.post("/v1/vault/admin/reindex")
    async def reindex(actor: ActorDep, request: Request):
        return {"chunks": svc(request).rebuild_index()}

    return app
