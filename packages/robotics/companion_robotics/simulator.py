"""A kinematic rover/head simulator with the safety behaviour a real body must also have.

Independent of any model: motion stops when commands go stale (watchdog), when the link
is reported lost, when a bumper or cliff sensor trips, or when the emergency stop is
latched (which then needs an explicit reset). Commands beyond the limits are rejected,
never clamped silently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from companion_core.errors import Conflict, ValidationFailed

from .contracts import MotionCommand, MotionLimits, Pose, RobotStatus, Sensors


@dataclass
class _Active:
    cmd: MotionCommand
    started_t: float
    ends_t: float
    remaining_m: float | None = None
    remaining_deg: float | None = None


@dataclass
class RoverSimulator:
    limits: MotionLimits = field(default_factory=MotionLimits)
    mode: str = "simulated"
    t: float = 0.0  # simulation clock (seconds)
    pose: Pose = field(default_factory=Pose)
    sensors: Sensors = field(default_factory=Sensors)
    state: str = "idle"
    reason: str = ""
    estop_latched: bool = False
    odometer_m: float = 0.0
    last_command_t: float | None = None
    last_heartbeat_t: float | None = None
    _active: _Active | None = None
    log: list[tuple[float, str]] = field(default_factory=list)

    # -- inputs ------------------------------------------------------------
    def heartbeat(self) -> None:
        self.last_heartbeat_t = self.t

    def apply(self, cmd: MotionCommand) -> RobotStatus:
        """Validate and start a bounded command. Raises on anything outside the envelope."""
        self.last_command_t = self.t
        self.last_heartbeat_t = self.t
        if cmd.kind == "heartbeat":
            return self.status()
        if cmd.kind == "stop":
            self._halt("idle", "stop requested")
            return self.status()
        if self.estop_latched:
            raise Conflict("emergency stop is latched; reset it physically/explicitly before moving")
        if not self.sensors.link_ok:
            raise Conflict("link is down; motion refused")
        if cmd.kind == "look":
            if cmd.look is None:
                raise ValidationFailed("look needs a direction")
            pan = {"left": 45.0, "right": -45.0, "centre": 0.0}.get(cmd.look, self.sensors.head_pan_deg)
            tilt = {"up": 20.0, "down": -20.0, "centre": 0.0}.get(cmd.look, self.sensors.head_tilt_deg)
            self.sensors.head_pan_deg, self.sensors.head_tilt_deg = pan, tilt
            self.state, self.reason = "idle", f"looking {cmd.look}"
            self._log(f"look {cmd.look}")
            return self.status()
        if cmd.kind == "dock":
            self._active = _Active(cmd, self.t, self.t + min(cmd.duration_s or 3.0, self.limits.max_command_duration_s))
            self.state, self.reason = "docking", "docking manoeuvre (simulated)"
            return self.status()
        # move / turn
        if abs(cmd.linear_mps) > self.limits.max_linear_mps + 1e-9:
            raise ValidationFailed(f"linear speed {cmd.linear_mps} m/s exceeds the limit {self.limits.max_linear_mps} m/s")
        if abs(cmd.angular_rps) > self.limits.max_angular_rps + 1e-9:
            raise ValidationFailed(f"angular speed {cmd.angular_rps} rad/s exceeds the limit {self.limits.max_angular_rps} rad/s")
        if cmd.duration_s > self.limits.max_command_duration_s + 1e-9:
            raise ValidationFailed(f"duration {cmd.duration_s}s exceeds the limit {self.limits.max_command_duration_s}s")
        if cmd.distance_m is not None and cmd.distance_m > self.limits.max_distance_m + 1e-9:
            raise ValidationFailed(f"distance {cmd.distance_m} m exceeds the limit {self.limits.max_distance_m} m")
        if cmd.kind == "move" and cmd.linear_mps > 0 and (self.sensors.bumper_front or self.sensors.cliff_front):
            raise Conflict("front bumper/cliff sensor is active; forward motion refused until cleared")
        if cmd.kind == "move" and cmd.linear_mps == 0 and cmd.angular_rps == 0:
            raise ValidationFailed("move needs a speed")
        if cmd.kind == "turn" and cmd.angular_rps == 0:
            raise ValidationFailed("turn needs an angular speed")
        duration = cmd.duration_s or self.limits.max_command_duration_s
        act = _Active(cmd, self.t, self.t + min(duration, self.limits.max_command_duration_s))
        if cmd.distance_m is not None and cmd.linear_mps:
            act.remaining_m = cmd.distance_m
        if cmd.angle_deg is not None and cmd.angular_rps:
            act.remaining_deg = abs(cmd.angle_deg)
        self._active = act
        self.state, self.reason = "moving", f"{cmd.kind} from {cmd.client_id or 'client'}"
        self._log(f"{cmd.kind} v={cmd.linear_mps} w={cmd.angular_rps}")
        return self.status()

    def link_lost(self) -> RobotStatus:
        self.sensors.link_ok = False
        self._halt("stopped_link", "network link lost")
        return self.status()

    def link_restored(self) -> RobotStatus:
        self.sensors.link_ok = True
        if self.state == "stopped_link":
            self.state, self.reason = "idle", "link restored; awaiting a new command"
        return self.status()

    def bumper(self, pressed: bool) -> RobotStatus:
        self.sensors.bumper_front = pressed
        if pressed:
            self._halt("stopped_bumper", "front bumper pressed")
        elif self.state == "stopped_bumper":
            self.state, self.reason = "idle", "bumper cleared"
        return self.status()

    def cliff(self, detected: bool) -> RobotStatus:
        self.sensors.cliff_front = detected
        if detected:
            self._halt("stopped_cliff", "cliff detected")
        elif self.state == "stopped_cliff":
            self.state, self.reason = "idle", "cliff cleared"
        return self.status()

    def estop(self) -> RobotStatus:
        self.estop_latched = True
        self._halt("estop", "emergency stop latched")
        return self.status()

    def reset(self) -> RobotStatus:
        if self.sensors.bumper_front or self.sensors.cliff_front:
            raise Conflict("clear the bumper/cliff condition before resetting")
        self.estop_latched = False
        self.state, self.reason = "idle", "reset"
        self._log("reset")
        return self.status()

    # -- time --------------------------------------------------------------
    def tick(self, dt: float) -> RobotStatus:
        """Advance the simulation; enforce the watchdog regardless of what anyone asked."""
        if dt <= 0:
            return self.status()
        steps = max(1, int(math.ceil(dt / 0.05)))
        h = dt / steps
        for _ in range(steps):
            self.t += h
            act = self._active
            if act is None:
                continue
            stale = self.last_heartbeat_t is None or (self.t - self.last_heartbeat_t) > self.limits.watchdog_timeout_s
            if stale:
                self._halt("stopped_watchdog", f"no command/heartbeat for more than {self.limits.watchdog_timeout_s}s")
                continue
            if self.t >= act.ends_t:
                self._halt("docked" if act.cmd.kind == "dock" else "idle", "command completed")
                continue
            cmd = act.cmd
            if cmd.kind in {"move", "turn"}:
                v, w = cmd.linear_mps, cmd.angular_rps
                self.pose.theta_deg = (self.pose.theta_deg + math.degrees(w * h)) % 360
                dx = v * h * math.cos(math.radians(self.pose.theta_deg))
                dy = v * h * math.sin(math.radians(self.pose.theta_deg))
                self.pose.x_m += dx
                self.pose.y_m += dy
                self.odometer_m += abs(v * h)
                if act.remaining_m is not None:
                    act.remaining_m -= abs(v * h)
                    if act.remaining_m <= 0:
                        self._halt("idle", "distance reached")
                        continue
                if act.remaining_deg is not None:
                    act.remaining_deg -= abs(math.degrees(w * h))
                    if act.remaining_deg <= 0:
                        self._halt("idle", "angle reached")
                        continue
            self.sensors.battery_pct = max(0.0, self.sensors.battery_pct - 0.001 * h)
        return self.status()

    # -- helpers -----------------------------------------------------------
    def _halt(self, state: str, reason: str) -> None:
        self._active = None
        self.state, self.reason = state, reason
        self._log(f"halt: {state} ({reason})")

    def _log(self, msg: str) -> None:
        self.log.append((round(self.t, 3), msg))
        if len(self.log) > 500:
            del self.log[:100]

    def status(self) -> RobotStatus:
        return RobotStatus(
            mode="simulated", state=self.state, reason=self.reason, pose=self.pose.model_copy(), sensors=self.sensors.model_copy(),  # type: ignore[arg-type]
            active_command=self._active.cmd if self._active else None,
            command_age_s=None if self.last_command_t is None else round(self.t - self.last_command_t, 3),
            last_heartbeat_age_s=None if self.last_heartbeat_t is None else round(self.t - self.last_heartbeat_t, 3),
            limits=self.limits, estop_latched=self.estop_latched, odometer_m=round(self.odometer_m, 4), sim_time_s=round(self.t, 3),
        )
