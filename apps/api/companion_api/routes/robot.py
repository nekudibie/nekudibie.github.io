"""Embodiment endpoints (simulation only). Movement needs robot.command; status needs robot.status.
The watchdog runs server-side on every worker tick and on every call here, so a client that
stops talking cannot leave the rover moving."""

from __future__ import annotations

from typing import Annotated, Any

from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import NotConfigured
from companion_robotics import MotionCommand
from fastapi import APIRouter, Depends, Request

from ..auth import require

router = APIRouter(prefix="/v1/robot")
Commander = Annotated[ClientIdentity, Depends(require(Permission.ROBOT_COMMAND))]
Watcher = Annotated[ClientIdentity, Depends(require(Permission.ROBOT_STATUS))]


def _robot(request: Request) -> Any:
    st = request.app.state.companion
    if st.robot is None:
        raise NotConfigured("robotics.mode is disabled")
    st.robot_tick()
    return st.robot


@router.get("/status")
async def status(identity: Watcher, request: Request):
    return _robot(request).status().model_dump()


@router.post("/command")
async def command(cmd: MotionCommand, identity: Commander, request: Request):
    robot = _robot(request)
    cmd = cmd.model_copy(update={"client_id": identity.client_id})
    return robot.apply(cmd).model_dump()


@router.post("/heartbeat")
async def heartbeat(identity: Commander, request: Request):
    robot = _robot(request)
    robot.heartbeat()
    return robot.status().model_dump()


@router.post("/stop")
async def stop(identity: Watcher, request: Request):
    """Stop is available to anyone who can even see the robot."""
    return _robot(request).apply(MotionCommand(kind="stop", client_id=identity.client_id)).model_dump()


@router.post("/estop")
async def estop(identity: Watcher, request: Request):
    return _robot(request).estop().model_dump()


@router.post("/reset")
async def reset(identity: Commander, request: Request):
    return _robot(request).reset().model_dump()


@router.post("/sim/{event}")
async def sim_event(event: str, identity: Annotated[ClientIdentity, Depends(require(Permission.ADMIN))], request: Request, value: bool = True):
    """Admin/test helper to inject simulated sensor and link events."""
    robot = _robot(request)
    if event == "link":
        return (robot.link_restored() if value else robot.link_lost()).model_dump()
    if event == "bumper":
        return robot.bumper(value).model_dump()
    if event == "cliff":
        return robot.cliff(value).model_dump()
    if event == "tick":
        return robot.tick(1.0).model_dump()
    from companion_core.errors import ValidationFailed

    raise ValidationFailed("event must be link, bumper, cliff or tick")
