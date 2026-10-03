"""Deterministic fixture models.

``FixtureProvider`` gives a usable demo without any model host: it recognises a
few intents, calls the real tool gateway (so permission checks are exercised) and
phrases replies from the real tool results. It is always labelled as a fixture.

``ScriptedProvider`` replays test-supplied chunks so tests can simulate anything a
model might emit, including hallucinated tools and malformed arguments.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from companion_contracts.health import DependencyStatus
from companion_core.ids import new_id

from .base import LLMChunk, ToolCall

_REMEMBER_RE = re.compile(r"^\s*(?:please\s+)?(?:remember|note|save)(?:\s+that|\s+this)?[:\s]+(.+)$", re.I | re.S)
_QUESTION_RE = re.compile(
    r"^\s*(what|when|which|who|where|did|do|does|have|has|was|were|is|are|how|search|find|look up|recall|tell me)\b", re.I
)
_TIME_RE = re.compile(r"\b(what time|the time|what('s| is) the date|today's date|what day)\b", re.I)
_WEATHER_RE = re.compile(r"\bweather|forecast|rain|umbrella\b", re.I)
_MATHS_RE = re.compile(r"(solve|simplify|differentiate|integrate|evaluate|calculate|what is)\s+(.+)", re.I)
_MEETING_ACTION_RE = re.compile(r"\b(action|actions|owner|deadline|follow[- ]?up)\b.*\bmeeting\b|\bmeeting\b.*\b(action|actions)\b", re.I)


def _last_user(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _last_tool(messages: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    for m in reversed(messages):
        if m.get("role") == "tool":
            return m.get("tool_name"), str(m.get("content", ""))
        if m.get("role") == "user":
            break
    return None, None


def _tool_available(tools: list[dict[str, Any]], name: str) -> bool:
    return any(t.get("function", {}).get("name") == name for t in tools)


def _unwrap(content: str) -> dict[str, Any]:
    """Tool results arrive wrapped as untrusted text; the JSON body sits between the markers."""
    m = re.search(r"<<<untrusted[^>]*>>>\n?(.*?)\n?<<<end untrusted>>>", content, re.S)
    body = m.group(1) if m else content
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else {"value": data}
    except json.JSONDecodeError:
        return {"text": body}


class FixtureProvider:
    is_fixture = True
    name = "fixture"
    model = "fixture-demo"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[LLMChunk]:
        user = _last_user(messages)
        tool_name, tool_content = _last_tool(messages)
        if tool_name is not None and tool_content is not None:
            text = self._phrase_result(tool_name, _unwrap(tool_content))
        else:
            call = self._choose_tool(user, tools)
            if call is not None:
                yield LLMChunk(tool_calls=[call])
                yield LLMChunk(done=True, done_reason="stop")
                return
            text = self._fallback(user)
        for piece in _stream_pieces(text):
            if cancel is not None and cancel.is_set():
                return
            yield LLMChunk(content=piece)
            await asyncio.sleep(0)
        yield LLMChunk(done=True, done_reason="stop", usage={"fixture": True})

    # -- intent selection ----------------------------------------------
    def _choose_tool(self, user: str, tools: list[dict[str, Any]]) -> ToolCall | None:
        m = _REMEMBER_RE.match(user)
        if m:
            text = m.group(1).strip()
            fm = re.match(r"^(?:that\s+)?my ([a-z][a-z ]{1,40}?) is (?:now )?(.+?)[.!]?$", text, re.I)
            if fm and _tool_available(tools, "fact_remember"):
                return ToolCall(id=new_id("call"), name="fact_remember", arguments={"subject": "owner", "predicate": fm.group(1).strip().lower(), "value": fm.group(2).strip()})
            dm = re.match(r"^(?:that\s+)?(?:we|i) decided (?:that )?(.+?)(?:\s+for (?:the )?(.+?) project)?[.!]?$", text, re.I)
            if dm and _tool_available(tools, "decision_record"):
                args = {"statement": dm.group(1).strip()}
                if dm.group(2):
                    args["project"] = dm.group(2).strip()
                return ToolCall(id=new_id("call"), name="decision_record", arguments=args)
            if _tool_available(tools, "memory_save"):
                kind = "decision" if re.search(r"\bdecid|decision\b", text, re.I) else "note"
                return ToolCall(id=new_id("call"), name="memory_save", arguments={"text": text, "kind": kind})
        if _TIME_RE.search(user) and _tool_available(tools, "clock_now"):
            return ToolCall(id=new_id("call"), name="clock_now", arguments={})
        if _WEATHER_RE.search(user) and _tool_available(tools, "weather_forecast"):
            day = "tomorrow" if "tomorrow" in user.lower() else ("week" if "week" in user.lower() else "today")
            return ToolCall(id=new_id("call"), name="weather_forecast", arguments={"day": day})
        if _MEETING_ACTION_RE.search(user) and _tool_available(tools, "meeting_query"):
            args: dict[str, Any] = {"query": user[:300]}
            nm = re.search(r"\bfrom (?:the |my |our )?(.+?) (?:meeting|sync|call|standup|retro)\b", user, re.I)
            if nm:
                args["meeting"] = nm.group(1).strip()
            return ToolCall(id=new_id("call"), name="meeting_query", arguments=args)
        mm = _MATHS_RE.search(user)
        if mm and _tool_available(tools, "maths") and re.search(r"[0-9=+\-*/^]", mm.group(2)):
            task = {"solve": "solve", "simplify": "simplify", "differentiate": "differentiate", "integrate": "integrate"}.get(
                mm.group(1).lower(), "evaluate"
            )
            expr = mm.group(2).strip().rstrip("?.")
            expr = re.sub(r"^(the\s+)?(equation|expression)\s+", "", expr, flags=re.I)
            return ToolCall(id=new_id("call"), name="maths", arguments={"expression": expr, "task": task})
        if _QUESTION_RE.match(user) and _tool_available(tools, "memory_search"):
            return ToolCall(id=new_id("call"), name="memory_search", arguments={"query": user[:300], "limit": 5})
        return None

    def _phrase_result(self, tool_name: str, data: dict[str, Any]) -> str:
        if data.get("error"):
            return f"I tried to use {tool_name} but it was refused: {data.get('error')}."
        if tool_name == "memory_search":
            hits = data.get("hits") or []
            facts = data.get("facts") or []
            decisions = data.get("decisions") or []
            if not hits and not facts and not decisions:
                return "I couldn't find any saved record about that in your memory vault, so I won't guess."
            if facts and not hits:
                f = facts[0]
                return f"Your {f['predicate']} is {f['value']} [{f['label']}]." + (f" ({len(facts)} facts matched.)" if len(facts) > 1 else "")
            if decisions and not hits:
                d = decisions[0]
                proj = f" for {d['project']}" if d.get("project") else ""
                return f"The current decision{proj} is: {d['statement']} [{d['label']}]." + (" Earlier versions are kept in history." if d.get("status") == "current" else "")
            parts = []
            for i, h in enumerate(hits[:2], start=1):
                body = (h.get("text") or h.get("snippet") or "").strip().replace("\n", " ")
                if len(body) > 220:
                    body = body[:217].rstrip() + "…"
                parts.append(f"“{body}” [S{i}]")
            lead = "From your saved records: " if len(hits) == 1 else "From your saved records, the closest matches are: "
            tail = f" ({len(hits)} match{'es' if len(hits) != 1 else ''} in total.)" if len(hits) > 2 else ""
            return lead + " ".join(parts) + tail
        if tool_name == "memory_save":
            return f"Saved as “{data.get('title', 'a note')}”. I'll be able to find it later and cite it."
        if tool_name == "fact_remember":
            tail = " That replaces what I had before; the old value stays in history." if data.get("replaced_previous_value") else ""
            return f"Noted: your {data.get('predicate')} is {data.get('value')}.{tail}"
        if tool_name == "decision_record":
            proj = f" for {data.get('project')}" if data.get("project") else ""
            return f"Decision recorded{proj}: {data.get('statement')}."
        if tool_name == "clock_now":
            return f"It's {data.get('time_local')} on {data.get('date_local')} ({data.get('timezone')})."
        if tool_name == "weather_forecast":
            return str(data.get("summary", "No forecast available."))
        if tool_name == "maths":
            return str(data.get("explanation") or data.get("result") or "I couldn't work that out.")
        if tool_name == "meeting_query":
            if data.get("ambiguous"):
                opts = "; ".join(f"{c['title']} on {c['date']}" for c in data.get("candidates", []))
                return f"I found more than one meeting with that name: {opts}. Which one do you mean?"
            acts = data.get("actions") or []
            if acts:
                parts = []
                for a in acts[:3]:
                    owner = f"owner {a['owner']}" if a.get("owner_known") else "owner not stated"
                    due = f", due {a['due_text']}" if a.get("due_text") else ", no deadline stated"
                    parts.append(f"{a['title']} ({owner}{due}) [{a['label']}]")
                when = f" from {acts[0].get('meeting')} on {acts[0].get('meeting_date')}" if acts[0].get("meeting") else ""
                return f"Draft actions{when}: " + "; ".join(parts) + ". These are unconfirmed until you accept them."
            hits = data.get("hits") or []
            if hits:
                return f"From the transcript: “{hits[0]['snippet']}” [{hits[0]['label']}]"
            if data.get("meetings"):
                return "I found the meeting but nothing in it matched that question."
            return "I have no recorded meetings matching that."
        if tool_name == "meeting_control":
            return f"Recording {data.get('status')}." if data.get("status") else "Done."
        return f"Done ({tool_name}): {json.dumps(data)[:300]}"

    def _fallback(self, user: str) -> str:
        return (
            "I'm running on the fixture model, so I can only do simple demo replies. "
            f"You said: “{user.strip()[:200]}”. "
            "Set llm.provider to ollama with a tool-capable model for real conversation."
        )

    async def health(self) -> DependencyStatus:
        return DependencyStatus(name="llm", status="fixture", detail="fixture model: scripted demo replies only")


class ScriptedProvider:
    """Replays scripted turns. Each turn is a list of LLMChunk; a dict is treated as a tool call."""

    is_fixture = True
    name = "scripted"
    model = "scripted-test"

    def __init__(self, turns: list[list[LLMChunk | dict[str, Any] | str]], *, delay_s: float = 0.0, fail_with: Exception | None = None) -> None:
        self.turns = list(turns)
        self.delay_s = delay_s
        self.fail_with = fail_with
        self.received: list[list[dict[str, Any]]] = []

    async def chat(self, messages, tools, *, cancel=None):  # type: ignore[no-untyped-def]
        self.received.append(messages)
        if self.fail_with is not None:
            raise self.fail_with
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        turn = self.turns.pop(0) if self.turns else ["(no scripted turn left)"]
        for item in turn:
            if cancel is not None and cancel.is_set():
                return
            if isinstance(item, str):
                yield LLMChunk(content=item)
            elif isinstance(item, dict):
                yield LLMChunk(tool_calls=[ToolCall(id=new_id("call"), name=item["name"], arguments=item.get("arguments", {}))])
            else:
                yield item
            await asyncio.sleep(0)
        yield LLMChunk(done=True, done_reason="stop")

    async def health(self) -> DependencyStatus:
        return DependencyStatus(name="llm", status="fixture", detail="scripted test model")


def _stream_pieces(text: str, size: int = 12) -> list[str]:
    words = text.split(" ")
    out, buf = [], ""
    for w in words:
        buf = (buf + " " + w) if buf else w
        if len(buf) >= size:
            out.append(buf + " ")
            buf = ""
    if buf:
        out.append(buf)
    if out:
        out[-1] = out[-1].rstrip(" ")
    return out
