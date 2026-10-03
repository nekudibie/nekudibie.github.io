"""Meeting recording endpoints: explicit, participant-aware, chunked and resumable."""

from __future__ import annotations

from typing import Annotated, Any

from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import NotFound, PermissionDenied, ValidationFailed
from companion_worker.queue import BACKGROUND
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require

router = APIRouter(prefix="/v1/meetings")
Recorder = Annotated[ClientIdentity, Depends(require(Permission.MEETING_RECORD))]
Reader = Annotated[ClientIdentity, Depends(require(Permission.MEETING_READ))]
MAX_CHUNK_BYTES = 20 * 1024 * 1024


class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=200)
    participants_informed: bool = Field(description="Must be true: everyone present knows the meeting is recorded")
    route: str = Field(default="personal", pattern=r"^(personal|employer_approved)$")


class ConfirmActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: str | None = Field(default=None, max_length=120)
    due_at: str | None = None
    title: str | None = Field(default=None, max_length=500)


def _st(request: Request) -> Any:
    return request.app.state.companion


def _own(st: Any, identity: ClientIdentity, recording_id: str) -> Any:
    rec = st.recordings.get(recording_id)
    if rec.client_id != identity.client_id and not identity.has(Permission.ADMIN):
        raise PermissionDenied("this recording belongs to another client")
    return rec


@router.post("", status_code=201)
async def start(body: StartBody, identity: Recorder, request: Request):
    st = _st(request)
    if not body.participants_informed:
        raise ValidationFailed("Recording requires confirmation that everyone present knows it is being recorded.")
    rec = st.recordings.create(client_id=identity.client_id, title=body.title, participants_informed=True, route=body.route)
    return rec.model_dump()


@router.get("")
async def list_recordings(identity: Reader, request: Request, status: str | None = None, limit: int = 50):
    st = _st(request)
    statuses = status.split(",") if status else None
    return [r.model_dump() for r in st.recordings.list(client_id=None if identity.has(Permission.ADMIN) else identity.client_id, status=statuses, limit=min(max(limit, 1), 200))]


@router.get("/{recording_id}")
async def get_recording(recording_id: str, identity: Reader, request: Request):
    st = _st(request)
    rec = _own(st, identity, recording_id)
    related = [j.model_dump() for j in st.queue.list(limit=200) if j.payload.get("recording_id") == recording_id]
    actions = await st.vault.list_actions(scopes=identity.memory_scopes, meeting_id=recording_id)
    return {"recording": rec.model_dump(), "chunks": len(st.recordings.chunks(recording_id)), "segments": len(st.recordings.segments(recording_id)),
            "jobs": related, "actions": [a.model_dump() for a in actions]}


@router.put("/{recording_id}/chunks/{seq}")
async def put_chunk(recording_id: str, seq: int, identity: Recorder, request: Request, x_content_sha256: Annotated[str | None, Header()] = None):
    st = _st(request)
    _own(st, identity, recording_id)
    data = await request.body()
    if len(data) > MAX_CHUNK_BYTES:
        raise ValidationFailed("chunk larger than 20 MB; send shorter chunks")
    return st.recordings.add_chunk(recording_id, seq, data, sha256_expected=x_content_sha256, client_id=identity.client_id).model_dump()


@router.post("/{recording_id}/pause")
async def pause(recording_id: str, identity: Recorder, request: Request):
    st = _st(request)
    _own(st, identity, recording_id)
    return st.recordings.pause(recording_id).model_dump()


@router.post("/{recording_id}/resume")
async def resume(recording_id: str, identity: Recorder, request: Request):
    st = _st(request)
    _own(st, identity, recording_id)
    return st.recordings.resume(recording_id).model_dump()


@router.post("/{recording_id}/stop")
async def stop(recording_id: str, identity: Recorder, request: Request):
    st = _st(request)
    _own(st, identity, recording_id)
    rec = st.recordings.stop(recording_id)
    job = st.queue.enqueue("transcribe_recording", {"recording_id": recording_id, "client_id": identity.client_id}, idempotency_key=f"transcribe:{recording_id}", priority=BACKGROUND, client_id=identity.client_id)
    return {"recording": rec.model_dump(), "job": job.model_dump()}


@router.post("/{recording_id}/cancel")
async def cancel(recording_id: str, identity: Recorder, request: Request):
    st = _st(request)
    _own(st, identity, recording_id)
    rec = st.recordings.cancel(recording_id)
    for j in st.queue.list(limit=200):
        if j.payload.get("recording_id") == recording_id and j.status in {"queued", "running"}:
            st.queue.cancel(j.id)
    return rec.model_dump()


@router.post("/{recording_id}/retry")
async def retry(recording_id: str, identity: Recorder, request: Request):
    st = _st(request)
    rec = _own(st, identity, recording_id)
    if rec.status not in {"stopped", "failed", "processing"}:
        raise ValidationFailed(f"recording is {rec.status}")
    job = st.queue.enqueue("transcribe_recording", {"recording_id": recording_id, "client_id": identity.client_id}, idempotency_key=f"transcribe:{recording_id}", priority=BACKGROUND, client_id=identity.client_id)
    if job.status in {"failed", "cancelled"}:
        job = st.queue.retry(job.id)
    return job.model_dump()


@router.get("/{recording_id}/segments")
async def segments(recording_id: str, identity: Reader, request: Request):
    st = _st(request)
    _own(st, identity, recording_id)
    return [s.model_dump() for s in st.recordings.segments(recording_id)]


@router.get("/{recording_id}/audio/{seq}")
async def audio(recording_id: str, seq: int, identity: Reader, request: Request):
    st = _st(request)
    _own(st, identity, recording_id)
    return Response(content=st.recordings.chunk_bytes(recording_id, seq), media_type="audio/wav", headers={"Cache-Control": "private, max-age=60"})


@router.post("/{recording_id}/actions/{action_id}/confirm")
async def confirm_action(recording_id: str, action_id: str, body: ConfirmActionBody, identity: Recorder, request: Request):
    """Turn a draft action into an open obligation (only the user does this, never the pipeline)."""
    st = _st(request)
    _own(st, identity, recording_id)
    fields: dict[str, Any] = {"status": "open"}
    if body.owner is not None:
        fields.update(owner=body.owner, owner_confidence=1.0)
    if body.due_at is not None:
        fields.update(due_at=body.due_at, due_confidence=1.0)
    if body.title:
        fields["title"] = body.title
    a = await st.vault.update_action(action_id, fields, actor=identity.client_id, scopes=identity.memory_scopes)
    if a.meeting_id != recording_id:
        raise NotFound("action does not belong to this recording")
    return a.model_dump()


@router.delete("/{recording_id}")
async def delete(recording_id: str, identity: Annotated[ClientIdentity, Depends(require(Permission.MEMORY_DELETE))], request: Request):
    st = _st(request)
    rec = _own(st, identity, recording_id)
    out = st.recordings.delete(recording_id)
    removed = []
    for doc_id in (rec.transcript_document_id, rec.summary_document_id):
        if doc_id:
            try:
                await st.vault.delete(doc_id, actor=identity.client_id, scopes=identity.memory_scopes, reason="recording deleted")
                removed.append(doc_id)
            except NotFound:
                pass
    return {**out, "vault_documents_deleted": removed}
