from __future__ import annotations

from companion_core.config import config_summary
from companion_core.version import version_info
from fastapi import APIRouter, Request

from ..auth import Identity
from .health import dependency_statuses

router = APIRouter(prefix="/v1")


@router.get("/settings")
async def settings(identity: Identity, request: Request):
    st = request.app.state.companion
    return {"config": config_summary(st.config), "warnings": st.warnings, "version": version_info("api")}


@router.get("/status")
async def status(identity: Identity, request: Request):
    st = request.app.state.companion
    deps = await dependency_statuses(request)
    return {
        "dependencies": [d.model_dump() for d in deps],
        "llm": {"provider": st.llm.name, "model": st.llm.model, "is_fixture": st.llm.is_fixture},
        "home": {"provider": st.home.name if st.home else None, "is_fixture": bool(st.home and st.home.is_fixture)},
        "vault_mode": getattr(st.vault, "mode", "unknown"),
        "uptime_s": st.uptime_s(),
        "active_turns": sum(len(v) for v in st.orchestrator.cancels._events.values()),
    }


@router.get("/audit/tools")
async def audit(identity: Identity, request: Request, limit: int = 50):
    st = request.app.state.companion
    return {"invocations": st.store.recent_tool_invocations(identity.client_id, limit=min(max(limit, 1), 200))}
