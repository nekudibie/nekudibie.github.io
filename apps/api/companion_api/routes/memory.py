from __future__ import annotations

from typing import Annotated

from companion_contracts.vault import (
    CorrectionRequest,
    DeleteResponse,
    Document,
    NoteCreate,
    SearchRequest,
    SearchResponse,
)
from companion_core.auth import ClientIdentity, Permission
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ..auth import require

router = APIRouter(prefix="/v1/memory")

Reader = Annotated[ClientIdentity, Depends(require(Permission.MEMORY_READ))]
Writer = Annotated[ClientIdentity, Depends(require(Permission.MEMORY_WRITE))]
Deleter = Annotated[ClientIdentity, Depends(require(Permission.MEMORY_DELETE))]


@router.post("/notes", response_model=Document, status_code=201)
async def create_note(note: NoteCreate, identity: Writer, request: Request):
    return await request.app.state.companion.vault.create_note(note, actor=identity.client_id)


@router.get("/notes", response_model=list[Document])
async def list_notes(identity: Reader, request: Request, kind: Annotated[list[str] | None, Query()] = None, limit: int = 50):
    st = request.app.state.companion
    return await st.vault.list_documents(scopes=identity.memory_scopes, kinds=kind, limit=min(max(limit, 1), 200))


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, identity: Reader, request: Request):
    return await request.app.state.companion.vault.search(req, scopes=identity.memory_scopes)


@router.get("/documents/{document_id}", response_model=Document)
async def get_document(document_id: str, identity: Reader, request: Request):
    return await request.app.state.companion.vault.get_document(document_id, scopes=identity.memory_scopes)


@router.get("/documents/{document_id}/history", response_model=list[Document])
async def history(document_id: str, identity: Reader, request: Request):
    return await request.app.state.companion.vault.history(document_id, scopes=identity.memory_scopes)


@router.post("/documents/{document_id}/correct", response_model=Document)
async def correct(document_id: str, req: CorrectionRequest, identity: Writer, request: Request):
    return await request.app.state.companion.vault.correct(document_id, req, actor=identity.client_id, scopes=identity.memory_scopes)


@router.delete("/documents/{document_id}", response_model=DeleteResponse)
async def delete(document_id: str, identity: Deleter, request: Request, reason: str = ""):
    return await request.app.state.companion.vault.delete(document_id, actor=identity.client_id, scopes=identity.memory_scopes, reason=reason)


@router.get("/stats")
async def stats(identity: Reader, request: Request):
    return await request.app.state.companion.vault.stats()


@router.get("/export")
async def export(identity: Deleter, request: Request):
    st = request.app.state.companion
    vault = st.vault
    if hasattr(vault, "service"):
        def gen():
            yield from vault.service.export_jsonl(scopes=identity.memory_scopes)
        return StreamingResponse(gen(), media_type="application/x-ndjson")
    docs = await vault.list_documents(scopes=identity.memory_scopes, limit=500)
    return StreamingResponse((d.model_dump_json() + "\n" for d in docs), media_type="application/x-ndjson")
