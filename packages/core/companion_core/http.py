"""Outbound HTTP defaults: explicit timeouts and bounded retries for idempotent calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


def make_async_client(
    base_url: str = "",
    *,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=headers or {}, follow_redirects=False)


async def retry(
    op: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.3,
    retry_on: tuple[type[BaseException], ...] = (httpx.TransportError,),
) -> T:
    """Retry an idempotent coroutine with exponential backoff (0.3s, 0.6s, 1.2s ...)."""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return await op()
        except retry_on as exc:  # noqa: PERF203
            last = exc
            if i == attempts - 1:
                break
            await asyncio.sleep(base_delay * (2**i))
    assert last is not None
    raise last
