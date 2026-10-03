from __future__ import annotations

import json

import httpx
import pytest
from companion_core.errors import UpstreamError, UpstreamUnavailable
from companion_integrations.llm.ollama import OllamaProvider


def _ndjson(lines):
    return "\n".join(json.dumps(x) for x in lines) + "\n"


def make_provider(handler):
    return OllamaProvider("http://ollama.test:11434", "demo-model", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_streams_content_and_tool_calls_in_ollama_shape():
    captured = {}

    def handler(request: httpx.Request):
        if request.url.path == "/api/chat":
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, text=_ndjson([
                {"model": "demo-model", "message": {"role": "assistant", "content": "Let me "}, "done": False},
                {"model": "demo-model", "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "memory_search", "arguments": {"query": "lantern"}}}]}, "done": False},
                {"model": "demo-model", "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop", "prompt_eval_count": 10, "eval_count": 5, "total_duration": 1200},
            ]))
        return httpx.Response(404)

    p = make_provider(handler)
    chunks = [c async for c in p.chat([{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "memory_search", "parameters": {}}}])]
    assert chunks[0].content == "Let me "
    assert chunks[1].tool_calls[0].name == "memory_search" and chunks[1].tool_calls[0].arguments == {"query": "lantern"}
    assert chunks[-1].done and chunks[-1].usage["eval_count"] == 5
    body = captured["body"]
    assert body["stream"] is True and body["tools"][0]["type"] == "function" and body["options"]["num_ctx"] == 8192 and body["keep_alive"] == "10m"


@pytest.mark.asyncio
async def test_missing_model_and_unreachable_host_map_to_typed_errors():
    def not_found(request):
        return httpx.Response(404, json={"error": "model 'demo-model' not found"})

    with pytest.raises(UpstreamError, match="not found"):
        async for _ in make_provider(not_found).chat([], []):
            pass

    def boom(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(UpstreamUnavailable, match="unreachable"):
        async for _ in make_provider(boom).chat([], []):
            pass

    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(UpstreamUnavailable, match="timed out"):
        async for _ in make_provider(slow).chat([], []):
            pass


@pytest.mark.asyncio
async def test_health_reports_model_presence_and_tool_capability():
    def handler(request):
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.0"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "demo-model:latest", "model": "demo-model:latest"}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"], "details": {}})
        return httpx.Response(404)

    h = await make_provider(handler).health()
    assert h.status == "degraded" and "tools" in h.detail

    def absent(request):
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.0"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        return httpx.Response(404)

    h = await make_provider(absent).health()
    assert h.status == "down" and "ollama pull demo-model" in h.detail
