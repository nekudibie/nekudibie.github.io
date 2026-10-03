from __future__ import annotations

import time

from companion_contracts.health import DependencyStatus, Readiness
from companion_core.clock import iso, now_utc
from companion_core.version import version_info
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request):
    st = request.app.state.companion
    return {"status": "ok", "service": "api", "version": version_info("api")["version"], "uptime_s": st.uptime_s()}


async def dependency_statuses(request: Request) -> list[DependencyStatus]:
    st = request.app.state.companion
    deps: list[DependencyStatus] = []
    t0 = time.monotonic()
    v = await st.vault.health()
    deps.append(DependencyStatus(name="vault", status="ok" if v.get("status") == "ok" else ("down" if v.get("status") == "down" else "degraded"),
                                 detail=f"mode={v.get('mode')} schema={v.get('schema', v.get('detail', ''))}", latency_ms=int((time.monotonic() - t0) * 1000)))
    deps.append(await st.llm.health())
    if st.home is None:
        deps.append(DependencyStatus(name="home", status="disabled", detail="home.provider: disabled"))
    else:
        deps.append(await st.home.health())
    for provider in st.extras.values():
        if hasattr(provider, "health"):
            deps.append(await provider.health())
    db_ok = st.store.db.integrity_ok()
    deps.append(DependencyStatus(name="brain_db", status="ok" if db_ok else "down", detail=st.store.db.schema_version() or ""))
    return deps


@router.get("/readyz", response_model=Readiness)
async def readyz(request: Request):
    deps = await dependency_statuses(request)
    # Ready means the API can serve: vault + brain DB must be up; the model may be down (degraded mode).
    core_ok = all(d.status in {"ok", "fixture"} for d in deps if d.name in {"vault", "brain_db"})
    return Readiness(ready=core_ok, service="api", dependencies=deps, checked_at=iso(now_utc()))


@router.get("/version")
async def version():
    return version_info("api")
