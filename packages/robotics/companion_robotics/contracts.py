"""Embodiment contracts: bounded high-level commands, status, and the stop conditions that
hold regardless of what any model asks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CommandKind = Literal["stop", "move", "turn", "look", "dock", "heartbeat"]
RobotState = Literal["idle", "moving", "looking", "docking", "docked", "stopped_watchdog", "stopped_link", "stopped_bumper", "stopped_cliff", "estop", "error"]


class MotionLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_linear_mps: float = 0.3
    max_angular_rps: float = 0.8
    max_command_duration_s: float = 5.0
    max_distance_m: float = 2.0
    watchdog_timeout_s: float = 0.5


class MotionCommand(BaseModel):
    """What a client (or, through the gateway, a model) may request. Every field is bounded;
    there is no raw PWM, no override, no way to change the limits from here."""

    model_config = ConfigDict(extra="forbid")
    kind: CommandKind
    linear_mps: float = Field(default=0.0, ge=-1.0, le=1.0)
    angular_rps: float = Field(default=0.0, ge=-3.0, le=3.0)
    duration_s: float = Field(default=0.0, ge=0.0, le=30.0)
    distance_m: float | None = Field(default=None, ge=0.0, le=10.0)
    angle_deg: float | None = Field(default=None, ge=-360.0, le=360.0)
    look: Literal["left", "right", "up", "down", "centre"] | None = None
    seq: int = Field(default=0, ge=0)
    client_id: str = ""


class Pose(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x_m: float = 0.0
    y_m: float = 0.0
    theta_deg: float = 0.0


class Sensors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bumper_front: bool = False
    cliff_front: bool = False
    battery_pct: float = 100.0
    link_ok: bool = True
    head_pan_deg: float = 0.0
    head_tilt_deg: float = 0.0


class RobotStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["simulated", "disabled", "live"] = "simulated"
    state: RobotState
    reason: str = ""
    pose: Pose
    sensors: Sensors
    active_command: MotionCommand | None = None
    command_age_s: float | None = None
    last_heartbeat_age_s: float | None = None
    limits: MotionLimits
    estop_latched: bool = False
    odometer_m: float = 0.0
    sim_time_s: float = 0.0
    note: str = "Simulation only: no motor output exists in this codebase. A real rover needs a microcontroller watchdog and a physical motor-power stop (docs/HARDWARE.md)."
