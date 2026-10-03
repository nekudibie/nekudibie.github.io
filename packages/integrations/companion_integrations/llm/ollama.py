"""Ollama adapter (verified against ollama/ollama docs/api.md, see docs/SOURCES.md).

* ``POST /api/chat`` with ``stream: true`` returns NDJSON; each line has
  ``message.content`` and optionally ``message.tool_calls[]`` with
  ``function.name`` and ``function.arguments`` (an object). The last line has
  ``done: true`` plus ``prompt_eval_count`` / ``eval_count`` / ``total_duration``.
* Tool results go back as ``{"role": "tool", "content": ..., "tool_name": ...}``.
* ``POST /api/show`` reports a ``capabilities`` list (e.g. ``["completion", "tools"]``)
  which we use to tell the user whether the chosen model can call tools at all.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from companion_contracts.health import DependencyStatus
from companion_core.errors import UpstreamError, UpstreamUnavailable
from companion_core.ids import new_id
from companion_core.logging import get_logger

from .base import LLMChunk, ToolCall

log = get_logger(__name__)


class OllamaProvider:
    is_fixture = False
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_s: float = 90.0,
        connect_timeout_s: float = 3.0,
        keep_alive: str = "10m",
        num_ctx: int = 8192,
        temperature: float = 0.3,
        think: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.think = think
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=connect_timeout_s, read=timeout_s, write=timeout_s, pool=connect_timeout_s),
            transport=transport,
        )
        self._capabilities: list[str] | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[LLMChunk]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx, "temperature": self.temperature},
        }
        if tools:
            payload["tools"] = tools
        if self.think is not None:
            payload["think"] = self.think
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise UpstreamError(f"ollama returned {resp.status_code}: {_error_text(body)}")
                async for line in resp.aiter_lines():
                    if cancel is not None and cancel.is_set():
                        return
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        log.warning("ollama sent a non-JSON line", extra={"length": len(line)})
                        continue
                    if "error" in data:
                        raise UpstreamError(f"ollama error: {data['error']}")
                    msg = data.get("message") or {}
                    calls = []
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        calls.append(ToolCall(id=new_id("call"), name=str(fn.get("name", "")), arguments=fn.get("arguments", {})))
                    done = bool(data.get("done"))
                    usage = {}
                    if done:
                        usage = {
                            k: data.get(k)
                            for k in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "eval_duration")
                            if data.get(k) is not None
                        }
                    yield LLMChunk(
                        content=msg.get("content") or "",
                        tool_calls=calls,
                        done=done,
                        done_reason=data.get("done_reason"),
                        usage=usage,
                    )
        except httpx.TimeoutException as exc:
            raise UpstreamUnavailable(f"ollama timed out ({exc.__class__.__name__})") from exc
        except httpx.TransportError as exc:
            raise UpstreamUnavailable(f"ollama unreachable at {self.base_url} ({exc.__class__.__name__})") from exc

    async def version(self) -> str:
        r = await self._client.get("/api/version")
        r.raise_for_status()
        return str(r.json().get("version", "?"))

    async def list_models(self) -> list[str]:
        r = await self._client.get("/api/tags")
        r.raise_for_status()
        return [m.get("name") or m.get("model") for m in r.json().get("models", [])]

    async def capabilities(self) -> list[str]:
        if self._capabilities is None:
            r = await self._client.post("/api/show", json={"model": self.model})
            if r.status_code == 404:
                raise UpstreamError(f"model {self.model!r} is not pulled on the Ollama host")
            r.raise_for_status()
            self._capabilities = list(r.json().get("capabilities") or [])
        return self._capabilities

    async def health(self) -> DependencyStatus:
        started = time.monotonic()
        try:
            ver = await self.version()
            models = await self.list_models()
            latency = int((time.monotonic() - started) * 1000)
            if self.model not in models and f"{self.model}:latest" not in models:
                return DependencyStatus(
                    name="llm", status="down", latency_ms=latency,
                    detail=f"ollama {ver} reachable but model {self.model!r} is not pulled (ollama pull {self.model})",
                )
            caps = await self.capabilities()
            if "tools" not in caps:
                return DependencyStatus(
                    name="llm", status="degraded", latency_ms=latency,
                    detail=f"ollama {ver}; model {self.model!r} does not report the 'tools' capability ({caps}); "
                    "memory/home tools will not be callable by the model",
                )
            return DependencyStatus(name="llm", status="ok", latency_ms=latency, detail=f"ollama {ver}; model {self.model}; capabilities {caps}")
        except (httpx.HTTPError, UpstreamError, ValueError) as exc:
            return DependencyStatus(
                name="llm", status="down", detail=f"{exc.__class__.__name__}: {str(exc)[:160]}",
                latency_ms=int((time.monotonic() - started) * 1000),
            )


def _error_text(body: bytes) -> str:
    try:
        return str(json.loads(body).get("error", body[:200]))
    except (ValueError, AttributeError):
        return body[:200].decode("utf-8", "replace")
