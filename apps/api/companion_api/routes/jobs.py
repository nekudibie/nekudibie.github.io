from __future__ import annotations

from typing import Annotated, Any

from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import PermissionDenied
from fastapi import APIRouter, Depends, Request

from ..auth import require

router = APIRouter(prefix="/v1/jobs")
Reader = Annotated[ClientIdentity, Depends(require(Permission.JOBS_READ))]


def _own(st: Any, identity: ClientIdentity, job_id: str) -> Any:
    job = st.queue.get(job_id)
    if job.client_id != identity.client_id and not identity.has(Permission.ADMIN):
        raise PermissionDenied("this job belongs to another client")
    return job


@router.get("")
async def list_jobs(identity: Reader, request: Request, status: str | None = None, limit: int = 50):
    st = request.app.state.companion
    statuses = status.split(",") if status else None
    jobs = st.queue.list(client_id=None if identity.has(Permission.ADMIN) else identity.client_id, status=statuses, limit=min(max(limit, 1), 200))
    return {"jobs": [j.model_dump() for j in jobs], "counts": st.queue.counts(), "worker_embedded": st.config.worker.embedded}


@router.get("/{job_id}")
async def get_job(job_id: str, identity: Reader, request: Request):
    st = request.app.state.companion
    job = _own(st, identity, job_id)
    return {"job": job.model_dump(), "events": [e.model_dump() for e in st.queue.events(job_id)]}


@router.post("/{job_id}/cancel")
async def cancel(job_id: str, identity: Reader, request: Request):
    st = request.app.state.companion
    _own(st, identity, job_id)
    return st.queue.cancel(job_id).model_dump()


@router.post("/{job_id}/retry")
async def retry(job_id: str, identity: Reader, request: Request):
    st = request.app.state.companion
    _own(st, identity, job_id)
    return st.queue.retry(job_id).model_dump()
