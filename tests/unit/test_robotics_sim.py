from __future__ import annotations

import pytest
from companion_core.errors import Conflict, ValidationFailed
from companion_robotics import MotionCommand, MotionLimits, RoverSimulator


def sim(**kw):  # type: ignore[no-untyped-def]
    return RoverSimulator(limits=MotionLimits(**kw))


def test_commands_outside_the_envelope_are_rejected_not_clamped():
    s = sim(max_linear_mps=0.3)
    with pytest.raises(ValidationFailed, match="exceeds the limit"):
        s.apply(MotionCommand(kind="move", linear_mps=0.5, duration_s=1))
    with pytest.raises(ValidationFailed, match="duration"):
        s.apply(MotionCommand(kind="move", linear_mps=0.2, duration_s=9))
    with pytest.raises(ValidationFailed, match="distance"):
        s.apply(MotionCommand(kind="move", linear_mps=0.2, duration_s=1, distance_m=5))
    assert s.state == "idle" and s.status().pose.x_m == 0.0


def test_stale_commands_stop_motion_within_the_watchdog():
    s = sim(watchdog_timeout_s=0.5)
    s.apply(MotionCommand(kind="move", linear_mps=0.2, duration_s=5))
    s.tick(0.4)
    assert s.state == "moving" and s.pose.x_m == pytest.approx(0.08, abs=0.01)
    s.tick(0.3)  # no heartbeat: 0.7 s since the last command
    assert s.state == "stopped_watchdog" and "no command/heartbeat" in s.reason
    x_at_stop = s.pose.x_m
    s.tick(2.0)
    assert s.pose.x_m == x_at_stop  # stays stopped
    assert x_at_stop < 0.2 * 0.5 + 0.02  # travelled at most watchdog_timeout worth of motion


def test_heartbeats_keep_a_bounded_command_alive_then_it_completes():
    s = sim(watchdog_timeout_s=0.5, max_command_duration_s=2.0)
    s.apply(MotionCommand(kind="move", linear_mps=0.1, duration_s=2.0))
    for _ in range(7):  # 2.1 s of simulated time with regular heartbeats
        s.tick(0.3)
        s.heartbeat()
    assert s.state == "idle" and s.reason == "command completed" and s.odometer_m == pytest.approx(0.2, abs=0.02)


def test_disconnection_stops_and_refuses_motion_until_restored():
    s = sim()
    s.apply(MotionCommand(kind="move", linear_mps=0.2, duration_s=3))
    s.link_lost()
    assert s.state == "stopped_link"
    with pytest.raises(Conflict, match="link is down"):
        s.apply(MotionCommand(kind="move", linear_mps=0.1, duration_s=1))
    s.link_restored()
    assert s.state == "idle"
    s.apply(MotionCommand(kind="turn", angular_rps=0.5, duration_s=3, angle_deg=45))  # 45 deg at 0.5 rad/s takes ~1.57 s
    for _ in range(12):
        s.tick(0.2)
        s.heartbeat()
    assert s.state == "idle" and s.reason == "angle reached" and 44 < s.pose.theta_deg < 52


def test_bumper_cliff_and_estop_latch():
    s = sim()
    s.apply(MotionCommand(kind="move", linear_mps=0.2, duration_s=3))
    s.bumper(True)
    assert s.state == "stopped_bumper"
    with pytest.raises(Conflict, match="bumper"):
        s.apply(MotionCommand(kind="move", linear_mps=0.1, duration_s=1))
    s.apply(MotionCommand(kind="move", linear_mps=-0.1, duration_s=1))  # reversing away is allowed
    s.bumper(False)
    s.estop()
    assert s.estop_latched and s.state == "estop"
    with pytest.raises(Conflict, match="emergency stop"):
        s.apply(MotionCommand(kind="look", look="left"))
    s.tick(1.0)
    assert s.state == "estop"
    s.reset()
    assert not s.estop_latched and s.state == "idle"
    s.cliff(True)
    assert s.state == "stopped_cliff"
    with pytest.raises(Conflict, match="clear the bumper/cliff"):
        s.estop() and s.reset()


def test_stop_and_look_are_always_available_and_status_is_honest():
    s = sim()
    s.apply(MotionCommand(kind="move", linear_mps=0.2, duration_s=3))
    st = s.apply(MotionCommand(kind="stop"))
    assert st.state == "idle" and st.active_command is None and st.mode == "simulated" and "no motor output" in st.note
    s.apply(MotionCommand(kind="look", look="up"))
    assert s.sensors.head_tilt_deg == 20.0
