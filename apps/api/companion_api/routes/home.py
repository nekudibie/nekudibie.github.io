from __future__ import annotations

from typing import Annotated, Any

from companion_contracts.home import CameraView, Entity, HomeCommandResult
from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import NotConfigured, PermissionDenied
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import require
from ..tools.gateway import ToolContext

router = APIRouter(prefix="/v1/home")
Reader = Annotated[ClientIdentity, Depends(require(Permission.HOME_READ))]
Controller = Annotated[ClientIdentity, Depends(require(Permission.HOME_CONTROL))]
Viewer = Annotated[ClientIdentity, Depends(require(Permission.CAMERA_VIEW))]


class CommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(turn_on|turn_off|toggle|activate)$")
    brightness_pct: int | None = Field(default=None, ge=0, le=100)
    color_temp_kelvin: int | None = Field(default=None, ge=1000, le=10000)


def _st(request: Request) -> Any:
    st = request.app.state.companion
    if st.home is None:
        raise NotConfigured("home.provider is disabled")
    return st


@router.get("/status")
async def status(identity: Reader, request: Request) -> dict[str, Any]:
    st = request.app.state.companion
    if st.home is None:
        return {"enabled": False, "provider": None, "is_fixture": False}
    h = await st.home.health()
    return {"enabled": True, "provider": st.home.name, "is_fixture": st.home.is_fixture, "health": h.model_dump(),
            "scenes": st.config.home.scenes, "cameras": st.config.home.cameras}


@router.get("/entities", response_model=list[Entity])
async def entities(identity: Reader, request: Request):
    st = _st(request)
    return await st.home_access.entities(identity)


@router.post("/entities/{entity_id}/command", response_model=HomeCommandResult)
async def command(entity_id: str, body: CommandBody, identity: Controller, request: Request):
    st = _st(request)
    ctx = ToolContext(identity=identity, state=st, route="ui")
    args = {"entity_id": entity_id, **body.model_dump(exclude_none=True)}
    outcome = await st.gateway.call(ctx, f"ui_{entity_id}", "home_control", args)
    if outcome.result is None:
        raise PermissionDenied(outcome.call_event.reason or "denied")
    if not outcome.result.ok:
        from companion_core.errors import UpstreamError
        raise UpstreamError(outcome.result.summary)
    d = outcome.result.data
    return HomeCommandResult(entity_id=d["entity_id"], action=d["action"], ok=d["ok"], new_state=d.get("new_state"), provider=d["provider"], is_fixture=d["is_fixture"], message=d.get("message", ""))


@router.get("/cameras", response_model=list[CameraView])
async def cameras(identity: Viewer, request: Request):
    st = _st(request)
    ents = [e for e in await st.home_access.entities(identity) if e.domain == "camera"]
    return [await st.home.camera_view(e.entity_id) for e in ents]


@router.get("/cameras/{entity_id}/view", response_model=CameraView)
async def camera_view(entity_id: str, identity: Viewer, request: Request):
    st = _st(request)
    if not st.home_access.is_allowed(identity, entity_id):
        raise PermissionDenied(f"{entity_id} is not on this client's allowlist")
    return await st.home.camera_view(entity_id)


@router.get("/cameras/{entity_id}/snapshot")
async def camera_snapshot(entity_id: str, identity: Viewer, request: Request):
    st = _st(request)
    if not st.home_access.is_allowed(identity, entity_id):
        raise PermissionDenied(f"{entity_id} is not on this client's allowlist")
    data, ctype = await st.home.camera_snapshot(entity_id)
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "no-store", "X-Companion-Fixture": "true" if st.home.is_fixture else "false"})


@router.get("/discover")
async def discover(identity: Annotated[ClientIdentity, Depends(require(Permission.ADMIN))], request: Request):
    """Admin helper: every entity the provider exposes, to build the allowlist from."""
    st = _st(request)
    ents = await st.home.list_entities()
    return {"provider": st.home.name, "is_fixture": st.home.is_fixture,
            "entities": [{"entity_id": e.entity_id, "friendly_name": e.friendly_name, "domain": e.domain, "state": e.state,
                          "allowed": st.home_access.is_allowed(identity, e.entity_id)} for e in ents]}
