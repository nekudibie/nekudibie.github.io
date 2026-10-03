"""Deterministic routing for commands that must work without a language model.

Stop/mute, the time, "turn on the desk lamp", "set study lighting" and "show the
front door camera" are matched here first. Anything else goes to the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from companion_core.auth import ClientIdentity

from .tools.home_access import HomeAccess

_STOP = re.compile(r"^\s*(stop|stop talking|stop speaking|be quiet|quiet|shush|hush|cancel|cancel that|never mind)\s*[.!]*\s*$", re.I)
_MUTE = re.compile(r"^\s*(mute|unmute)(\s+the)?(\s+mic(rophone)?)?\s*[.!]*\s*$", re.I)
_TIME = re.compile(r"^\s*(what(?:'s| is) the time|what time is it|time please|what(?:'s| is) today's date|what day is it)\s*[?.!]*\s*$", re.I)
_CAMERA = re.compile(r"^\s*(?:show|open|display|bring up)(?:\s+me)?(?:\s+the)?\s+(.+?)(?:\s+(?:camera|cam|feed))?\s*[.!?]*\s*$", re.I)
_ONOFF_A = re.compile(r"^\s*(?:turn|switch|put)\s+(on|off)\s+(?:the\s+|my\s+)?(.+?)\s*(?:please)?\s*[.!]*\s*$", re.I)
_ONOFF_B = re.compile(r"^\s*(?:turn|switch|put)\s+(?:the\s+|my\s+)?(.+?)\s+(on|off)\s*(?:please)?\s*[.!]*\s*$", re.I)
_DIM = re.compile(r"^\s*(?:dim|brighten|set)\s+(?:the\s+|my\s+)?(.+?)\s+to\s+(\d{1,3})\s*(?:%|percent)(?:\s+brightness)?\s*[.!]*\s*$", re.I)
_SCENE = re.compile(r"^\s*(?:set|activate|switch to|start|put on)\s+(?:the\s+)?(.+?)(?:\s+(?:scene|lighting|lights|mode))?\s*(?:please)?\s*[.!]*\s*$", re.I)


@dataclass
class Route:
    kind: str  # control | tool | reply
    action: str | None = None
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    reply: str | None = None
    ui_events: list[dict[str, Any]] = field(default_factory=list)


_REC_START = re.compile(r"^\s*(?:start|begin)\s+(?:a\s+)?recording(?:\s+(?:this|the)\s+meeting)?(?:\s+called\s+(.+?))?\s*[.!]*\s*$", re.I)
_REC_CTL = re.compile(r"^\s*(stop|pause|resume|end|finish)\s+(?:the\s+)?recording(?:\s+(?:this|the)\s+meeting)?\s*[.!]*\s*$", re.I)


class DeterministicRouter:
    def __init__(self, home: HomeAccess, recordings: Any = None) -> None:
        self.home = home
        self.recordings = recordings

    async def match(self, text: str, identity: ClientIdentity) -> Route | None:
        t = text.strip()
        if len(t) > 160:
            return None
        if _STOP.match(t):
            return Route(kind="control", action="stop", reply="Stopped.")
        m = _MUTE.match(t)
        if m:
            muted = m.group(1).lower() == "mute"
            reply = (
                "Microphone muted in software. Use the hardware switch for a guaranteed cut." if muted else "Microphone unmuted."
            )
            return Route(kind="control", action="mute" if muted else "unmute", reply=reply,
                         ui_events=[{"action": "notify", "payload": {"mute": muted, "software_only": True}}])
        if _TIME.match(t):
            return Route(kind="tool", tool="clock_now", args={})
        m = _REC_START.match(t)
        if m:
            title = (m.group(1) or "").strip()
            return Route(
                kind="reply",
                reply="Before I record, confirm on the Jobs page that everyone present knows this meeting is being recorded. The record button is there.",
                ui_events=[{"action": "open_panel", "payload": {"panel": "jobs", "intent": "start_recording", "title": title, "requires_consent": True}}],
            )
        m = _REC_CTL.match(t)
        if m:
            action = {"stop": "stop", "end": "stop", "finish": "stop", "pause": "pause", "resume": "resume"}[m.group(1).lower()]
            return Route(kind="tool", tool="meeting_control", args={"action": action})
        if not self.home.enabled:
            return None

        m = _DIM.match(t)
        if m:
            res = await self.home.resolve(m.group(1), identity, domains={"light"})
            if res.entity:
                pct = max(0, min(100, int(m.group(2))))
                return Route(kind="tool", tool="home_control", args={"entity_id": res.entity.entity_id, "action": "turn_on", "brightness_pct": pct})
            return await self._unresolved(m.group(1), identity, {"light"})

        for pat, grp_state, grp_name in ((_ONOFF_A, 1, 2), (_ONOFF_B, 2, 1)):
            m = pat.match(t)
            if m:
                name = m.group(grp_name)
                res = await self.home.resolve(name, identity, domains={"light", "switch", "input_boolean", "scene"})
                if res.entity and res.entity.domain == "scene":
                    if m.group(grp_state).lower() == "on":
                        return Route(kind="tool", tool="home_control", args={"entity_id": res.entity.entity_id, "action": "activate"})
                    return Route(kind="reply", reply=f"{res.entity.friendly_name} is a scene; scenes can be activated but not turned off.")
                if res.entity:
                    action = "turn_on" if m.group(grp_state).lower() == "on" else "turn_off"
                    return Route(kind="tool", tool="home_control", args={"entity_id": res.entity.entity_id, "action": action})
                return await self._unresolved(name, identity, {"light", "switch", "input_boolean"})

        m = _CAMERA.match(t)
        if m:
            res = await self.home.resolve(m.group(1), identity, domains={"camera"})
            if res.entity:
                return Route(kind="tool", tool="camera_show", args={"camera": res.entity.entity_id})
            if re.search(r"\b(camera|cam|feed)\b", t, re.I):
                return await self._unresolved(m.group(1), identity, {"camera"})

        m = _SCENE.match(t)
        if m:
            res = await self.home.resolve(m.group(1), identity, domains={"scene"})
            if res.entity:
                return Route(kind="tool", tool="home_control", args={"entity_id": res.entity.entity_id, "action": "activate"})
        return None

    async def _unresolved(self, name: str, identity: ClientIdentity, domains: set[str]) -> Route:
        ents = [e for e in await self.home.entities(identity) if e.domain in domains]
        known = ", ".join(sorted(e.friendly_name for e in ents)) or "none"
        return Route(kind="reply", reply=f"I don't know a device called “{name.strip()}”. Devices I can use: {known}.")
