from __future__ import annotations

from fastapi import APIRouter, Request

from ..auth import Identity

router = APIRouter(prefix="/v1")


@router.get("/me")
async def me(identity: Identity, request: Request):
    st = request.app.state.companion
    return {
        "client_id": identity.client_id,
        "role": identity.role,
        "label": identity.label,
        "permissions": sorted(p.value for p in identity.permissions),
        "memory_scopes": sorted(identity.memory_scopes),
        "tools": [s.name for s in st.gateway.specs_for(identity)],
        "instance": st.config.instance.name,
        "owner_name": st.config.instance.owner_name,
        "timezone": st.config.instance.timezone,
    }


@router.get("/tools")
async def tools(identity: Identity, request: Request):
    st = request.app.state.companion
    return {"tools": [s.model_dump() for s in st.gateway.specs_for(identity, include_disabled=True)]}
