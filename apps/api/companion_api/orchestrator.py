"""Turn processing: deterministic routes first, then the model with the tool gateway.

Produces a stream of typed events (see companion_contracts.events). Every path
persists what happened, including partial output when a client disconnects.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from companion_contracts.common import Source
from companion_contracts.events import (
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    StateEvent,
    TokenEvent,
    UIEvent,
)
from companion_core.auth import ClientIdentity
from companion_core.errors import (
    Cancelled,
    CompanionError,
    PermissionDenied,
    UpstreamError,
    UpstreamUnavailable,
)
from companion_core.ids import new_id
from companion_core.logging import get_logger
from pydantic import BaseModel

from .memory_extractor import extract_candidates
from .prompting import system_prompt, wrap_untrusted
from .router import Route
from .tools.gateway import ToolContext

if TYPE_CHECKING:
    from .state import AppState

log = get_logger(__name__)


class CancelRegistry:
    """Tracks in-flight turns per conversation so 'stop' and /cancel can interrupt them."""

    def __init__(self) -> None:
        self._events: dict[str, set[asyncio.Event]] = {}

    def register(self, conversation_id: str) -> asyncio.Event:
        ev = asyncio.Event()
        self._events.setdefault(conversation_id, set()).add(ev)
        return ev

    def release(self, conversation_id: str, ev: asyncio.Event) -> None:
        s = self._events.get(conversation_id)
        if s:
            s.discard(ev)
            if not s:
                self._events.pop(conversation_id, None)

    def cancel(self, conversation_id: str, *, except_event: asyncio.Event | None = None) -> int:
        n = 0
        for ev in list(self._events.get(conversation_id, ())):
            if ev is not except_event and not ev.is_set():
                ev.set()
                n += 1
        return n

    def active(self, conversation_id: str) -> int:
        return len(self._events.get(conversation_id, ()))


class Orchestrator:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self.cancels = CancelRegistry()

    # -- public ----------------------------------------------------------
    async def run_turn(
        self,
        identity: ClientIdentity,
        conversation_id: str,
        text: str,
        *,
        input_mode: str = "text",
        client_capabilities: list[str] | None = None,
    ) -> AsyncIterator[BaseModel]:
        st = self.state
        conv = st.store.get_conversation(conversation_id)
        if conv.client_id != identity.client_id and not identity.has(st.perm.ADMIN):
            raise PermissionDenied("this conversation belongs to another client")
        started = time.monotonic()
        user_msg = st.store.add_message(conversation_id, "user", text, meta={"input_mode": input_mode})
        st.store.set_title_if_empty(conversation_id, text)
        await self._propose_candidates(identity, text, user_msg.id)
        cancel = self.cancels.register(conversation_id)
        ctx = ToolContext(identity=identity, state=st, conversation_id=conversation_id, client_capabilities=client_capabilities or [])
        collected = Collected()
        try:
            route = await st.router.match(text, identity)
            if route is not None:
                ctx.route = "deterministic"
                async for ev in self._run_route(ctx, route, collected, cancel):
                    yield ev
                route_name = "deterministic"
            else:
                async for ev in self._run_llm(ctx, text, collected, cancel):
                    yield ev
                route_name = "fixture_llm" if st.llm.is_fixture else "llm"
            msg = st.store.add_message(
                conversation_id, "assistant", collected.text, sources=collected.sources,
                meta={"route": route_name, "model": st.llm.model, "usage": collected.usage, "tool_calls": collected.tool_names},
            )
            if collected.sources:
                yield SourcesEvent(sources=collected.sources)
            yield StateEvent(state="idle")
            yield DoneEvent(message_id=msg.id, route=route_name, model=st.llm.model, usage=collected.usage,  # type: ignore[arg-type]
                            duration_ms=int((time.monotonic() - started) * 1000))
        except Cancelled:
            msg = st.store.add_message(conversation_id, "assistant", collected.text, sources=collected.sources, meta={"cancelled": True})
            yield StateEvent(state="idle", detail="cancelled")
            yield DoneEvent(message_id=msg.id, route="llm", model=st.llm.model, usage={"cancelled": True}, duration_ms=int((time.monotonic() - started) * 1000))
        except UpstreamUnavailable as exc:
            text_out = "The language model is not reachable right now. Basic commands (time, lights, scenes, stop) still work."
            st.store.add_message(conversation_id, "assistant", text_out, meta={"error": "llm_unavailable", "detail": exc.message})
            yield ErrorEvent(code="llm_unavailable", message=f"{text_out} ({exc.message})", recoverable=True)
            yield StateEvent(state="offline", detail=exc.message)
        except UpstreamError as exc:
            st.store.add_message(conversation_id, "assistant", "The model returned an error.", meta={"error": "llm_error", "detail": exc.message})
            yield ErrorEvent(code="llm_error", message=exc.message, recoverable=True)
            yield StateEvent(state="error", detail=exc.message)
        except asyncio.CancelledError:
            # client went away mid-stream: keep what we have, then re-raise so the server tidies up
            st.store.add_message(conversation_id, "assistant", collected.text, sources=collected.sources, meta={"interrupted": True})
            raise
        finally:
            self.cancels.release(conversation_id, cancel)

    def cancel(self, conversation_id: str) -> int:
        return self.cancels.cancel(conversation_id)

    async def _propose_candidates(self, identity: ClientIdentity, text: str, message_id: str) -> None:
        """Store inferred facts as review candidates (never confirmed automatically)."""
        if not identity.has(self.state.perm.MEMORY_WRITE) or "owner" not in identity.memory_scopes:
            return
        try:
            from companion_vault.structured import FactCreate

            for c in extract_candidates(text):
                existing = await self.state.vault.list_facts(scopes=identity.memory_scopes, subject=c.subject, predicate=c.predicate, include_candidates=True)
                if any(f.value.strip().lower() == c.value.lower() for f in existing):
                    continue
                await self.state.vault.add_fact(
                    FactCreate(subject=c.subject, predicate=c.predicate, value=c.value, status="candidate", confidence=c.confidence,
                               trust="inferred", evidence_message_id=message_id, evidence_quote=c.quote[:1000]),
                    actor="extractor",
                )
        except Exception:  # noqa: BLE001 - extraction must never break a turn
            log.exception("candidate extraction failed")

    # -- deterministic ---------------------------------------------------
    async def _run_route(self, ctx: ToolContext, route: Route, collected: Collected, cancel: asyncio.Event) -> AsyncIterator[BaseModel]:
        if route.kind == "control":
            if route.action == "stop":
                n = self.cancels.cancel(ctx.conversation_id or "", except_event=cancel)
                collected.text = "Stopped." if n else "Nothing to stop."
                yield UIEvent(action="notify", payload={"stop_speaking": True, "cancelled_turns": n})
            else:
                collected.text = route.reply or ""
                for ev in route.ui_events:
                    yield UIEvent(**ev)
            yield TokenEvent(text=collected.text)
            return
        if route.kind == "reply":
            collected.text = route.reply or ""
            yield TokenEvent(text=collected.text)
            return
        assert route.tool
        yield StateEvent(state="tool_running", detail=route.tool)
        outcome = await self.state.gateway.call(ctx, new_id("call"), route.tool, route.args)
        yield outcome.call_event
        collected.tool_names.append(route.tool)
        if outcome.result_event is None:
            collected.text = f"I can't do that: {outcome.call_event.reason}."
            yield TokenEvent(text=collected.text)
            return
        yield outcome.result_event
        assert outcome.result is not None
        for ev in outcome.result.ui_events:
            yield UIEvent(**ev)
        collected.sources.extend(outcome.result.sources)
        collected.text = _phrase_route_result(route.tool, outcome.result)
        yield TokenEvent(text=collected.text)

    # -- model -----------------------------------------------------------
    async def _run_llm(self, ctx: ToolContext, text: str, collected: Collected, cancel: asyncio.Event) -> AsyncIterator[BaseModel]:
        st = self.state
        tz = ZoneInfo(st.config.instance.timezone)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": system_prompt(
                    owner_name=st.config.instance.owner_name, identity=ctx.identity,
                    now_local=st.clock.now().astimezone(tz), timezone=st.config.instance.timezone,
                    model_is_fixture=st.llm.is_fixture,
                ),
            }
        ]
        for m in st.store.recent_turns(ctx.conversation_id or "", max_messages=20):
            if m.role in {"user", "assistant"} and m.content:
                messages.append({"role": m.role, "content": m.content})
        if not messages or messages[-1].get("content") != text or messages[-1].get("role") != "user":
            messages.append({"role": "user", "content": text})
        specs = st.gateway.specs_for(ctx.identity)
        tools = [s.to_ollama() for s in specs]
        source_counter = 0

        for round_no in range(st.config.llm.max_tool_rounds + 1):
            yield StateEvent(state="thinking", detail=f"round {round_no + 1}")
            round_text = ""
            pending_calls = []
            async for chunk in st.llm.chat(messages, tools, cancel=cancel):
                if cancel.is_set():
                    raise Cancelled("turn cancelled")
                if chunk.content:
                    round_text += chunk.content
                    collected.text += chunk.content
                    yield TokenEvent(text=chunk.content)
                if chunk.tool_calls:
                    pending_calls.extend(chunk.tool_calls)
                if chunk.done:
                    collected.usage = chunk.usage or collected.usage
            if cancel.is_set():
                raise Cancelled("turn cancelled")
            if not pending_calls:
                return
            if round_no >= st.config.llm.max_tool_rounds:
                note = " I stopped after several tool steps without a final answer."
                collected.text += note
                yield TokenEvent(text=note)
                return
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": round_text, "tool_calls": []}
            tool_msgs: list[dict[str, Any]] = []
            for call in pending_calls[:6]:
                assistant_msg["tool_calls"].append({"function": {"name": call.name, "arguments": call.arguments if isinstance(call.arguments, dict) else {}}})
                yield StateEvent(state="tool_running", detail=call.name)
                outcome = await st.gateway.call(ctx, call.id, call.name, call.arguments)
                yield outcome.call_event
                collected.tool_names.append(call.name)
                if outcome.result_event is not None:
                    yield outcome.result_event
                if outcome.result is not None:
                    for ev in outcome.result.ui_events:
                        yield UIEvent(**ev)
                    if outcome.result.sources:
                        relabelled = []
                        for s in outcome.result.sources:
                            source_counter += 1
                            relabelled.append(s.model_copy(update={"label": f"S{source_counter}"}))
                        collected.sources.extend(relabelled)
                        content = _relabel_content(outcome.model_content, outcome.result.sources, relabelled)
                    else:
                        content = outcome.model_content
                else:
                    content = outcome.model_content
                tool_msgs.append({"role": "tool", "tool_name": call.name, "content": wrap_untrusted(content, origin=f"tool:{call.name}", source_id=call.id)})
            messages.append(assistant_msg)
            messages.extend(tool_msgs)


class Collected:
    def __init__(self) -> None:
        self.text = ""
        self.sources: list[Source] = []
        self.usage: dict[str, Any] = {}
        self.tool_names: list[str] = []


def _relabel_content(content: str, old: list[Source], new: list[Source]) -> str:
    for o, n in zip(old, new, strict=True):
        if o.label != n.label:
            content = content.replace(f'"label": "{o.label}"', f'"label": "{n.label}"')
    return content


def _phrase_route_result(tool: str, result: Any) -> str:
    if not result.ok:
        return f"That didn't work: {result.summary}."
    if tool == "clock_now":
        d = result.data
        return f"It's {d.get('time_local')} on {d.get('date_local')}."
    if tool == "home_control":
        return result.summary[0].upper() + result.summary[1:] + "."
    if tool == "camera_show":
        return result.summary[0].upper() + result.summary[1:] + "."
    return result.summary or "Done."


__all__ = ["Orchestrator", "CancelRegistry", "CompanionError"]
