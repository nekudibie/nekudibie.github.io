from __future__ import annotations

import asyncio

import pytest
from companion_api.state import build_state
from companion_integrations.llm.base import LLMChunk
from companion_integrations.llm.fixture import ScriptedProvider


class SlowProvider(ScriptedProvider):
    async def chat(self, messages, tools, *, cancel=None):  # type: ignore[no-untyped-def]
        for i in range(50):
            if cancel is not None and cancel.is_set():
                return
            yield LLMChunk(content=f"w{i} ")
            await asyncio.sleep(0.02)
        yield LLMChunk(done=True)


@pytest.mark.asyncio
async def test_cancel_stops_stream_and_persists_partial(cfg):
    state = build_state(cfg, llm=SlowProvider([]))
    identity = state.tokens.lookup("desk-test-token-0123456789")
    conv = state.store.create_conversation(identity.client_id)
    seen = []
    cancelled = False

    async def consume():
        nonlocal cancelled
        async for ev in state.orchestrator.run_turn(identity, conv.id, "talk for a long time"):
            seen.append(ev)
            if not cancelled and sum(1 for e in seen if e.type == "token") == 3:
                cancelled = True
                assert state.orchestrator.cancel(conv.id) == 1

    await asyncio.wait_for(consume(), timeout=5)
    tokens = [e for e in seen if e.type == "token"]
    assert 3 <= len(tokens) <= 5
    done = [e for e in seen if e.type == "done"][0]
    assert done.usage.get("cancelled") is True
    msgs = state.store.list_messages(conv.id)
    assert msgs[-1].role == "assistant" and msgs[-1].meta.get("cancelled") and msgs[-1].content.startswith("w0")
    assert state.orchestrator.cancels.active(conv.id) == 0


@pytest.mark.asyncio
async def test_stop_phrase_cancels_other_turn(cfg):
    state = build_state(cfg, llm=SlowProvider([]))
    identity = state.tokens.lookup("desk-test-token-0123456789")
    conv = state.store.create_conversation(identity.client_id)
    first = []

    async def long_turn():
        async for ev in state.orchestrator.run_turn(identity, conv.id, "go on and on"):
            first.append(ev)

    task = asyncio.create_task(long_turn())
    await asyncio.sleep(0.1)
    stop_events = [ev async for ev in state.orchestrator.run_turn(identity, conv.id, "stop")]
    await asyncio.wait_for(task, timeout=5)
    assert any(e.type == "token" and e.text == "Stopped." for e in stop_events)
    assert [e for e in first if e.type == "done"][0].usage.get("cancelled") is True
