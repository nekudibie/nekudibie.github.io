# ADR 0010: One bounded embodiment contract, simulated until hardware exists

**Status:** accepted (2026-10-03)

**Context.** The same assistant identity should later have a desk client, a carried client
and a rover. Motion must be safe regardless of what a model says, and nothing should pretend a
rover is a walking robot or that software is a certified stop.

**Decision.** `companion_robotics.contracts.MotionCommand` is the only motion request type:
kind (stop/move/turn/look/dock/heartbeat), bounded speeds, duration, distance and angle, no
raw actuator fields. Limits (`MotionLimits`) are configuration on the brain. Any command
outside the envelope is rejected, never clamped. The simulator enforces: watchdog stop on
stale commands, stop on link loss, bumper/cliff stops that refuse forward motion until
cleared, and a latched emergency stop that needs an explicit reset. Stop is available to any
authenticated client with `robot.status`; movement needs `robot.command`; sensor injection is
admin-only. A real body must meet the same contract on a microcontroller with its own watchdog
and a physical motor-power switch; Nav2 or similar adds a software layer on top, not a
replacement.

**Consequences.** Models can only ask for small, bounded actions; clients cannot leave the
rover moving by disconnecting; the live-hardware phase is a separate, validated project.
