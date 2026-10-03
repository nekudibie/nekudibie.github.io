"""Scryfall adapter following its API rules (docs/SOURCES.md): ``User-Agent`` and ``Accept``
headers on every request, at most 10 requests per second (we space calls by 120 ms), and a
local cache of at least 24 hours. Card names and legalities are Scryfall's; nothing is invented."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
from companion_contracts.health import DependencyStatus
from companion_core.clock import Clock, SystemClock, iso, parse_iso
from companion_core.errors import UpstreamError, UpstreamUnavailable

from .base import Card, CardLookup


class ScryfallProvider:
    name = "scryfall"
    is_fixture = False

    def __init__(self, cache_dir: Path, *, user_agent: str, cache_ttl_s: int = 86400, timeout_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None,
                 clock: Clock | None = None, base_url: str = "https://api.scryfall.com", min_interval_s: float = 0.12) -> None:
        self.cache_dir = cache_dir
        self.cache_ttl_s = cache_ttl_s
        self.clock = clock or SystemClock()
        self.min_interval_s = min_interval_s
        self._last_call = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(base_url=base_url, headers={"User-Agent": user_agent, "Accept": "application/json;q=0.9,*/*;q=0.8"},
                                         timeout=httpx.Timeout(connect=3.0, read=timeout_s, write=timeout_s, pool=3.0), transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _cache_file(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() else "_" for ch in key.lower())[:120]
        return self.cache_dir / f"{safe}.json"

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        p = self._cache_file(key)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
        if (self.clock.now() - parse_iso(data["fetched_at"])).total_seconds() > self.cache_ttl_s:
            return None
        return data

    def _write_cache(self, key: str, data: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file(key).write_text(json.dumps(data), encoding="utf-8")

    async def _get(self, path: str, params: dict[str, Any]) -> httpx.Response:
        async with self._lock:  # polite pacing: never more than ~8 requests/second
            wait = self.min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                r = await self._client.get(path, params=params)
            except httpx.TimeoutException as exc:
                raise UpstreamUnavailable("Scryfall timed out") from exc
            except httpx.TransportError as exc:
                raise UpstreamUnavailable(f"Scryfall unreachable ({exc.__class__.__name__})") from exc
            finally:
                self._last_call = time.monotonic()
        if r.status_code == 429:
            raise UpstreamError("Scryfall rate limit hit (429); slow down")
        return r

    @staticmethod
    def _to_card(d: dict[str, Any], fetched_at: str) -> Card:
        return Card(
            name=d.get("name", ""), oracle_id=d.get("oracle_id"), scryfall_id=d.get("id"), mana_cost=d.get("mana_cost"), cmc=d.get("cmc"), type_line=d.get("type_line", ""),
            oracle_text=d.get("oracle_text") or " // ".join(f.get("oracle_text", "") for f in d.get("card_faces", [])), colors=d.get("colors") or [],
            color_identity=d.get("color_identity") or [], legalities=d.get("legalities") or {}, set_code=d.get("set"), set_name=d.get("set_name"),
            scryfall_uri=d.get("scryfall_uri"), fetched_at=fetched_at,
        )

    async def lookup(self, name: str) -> CardLookup:
        key = f"named:{name.strip()}"
        cached = self._read_cache(key)
        if cached:
            if cached.get("ambiguous"):
                return CardLookup(query=name, ambiguous=cached["ambiguous"], from_cache=True, provider=self.name)
            if cached.get("not_found"):
                return CardLookup(query=name, not_found=True, from_cache=True, provider=self.name)
            return CardLookup(query=name, card=Card.model_validate(cached["card"]), from_cache=True, provider=self.name)
        now = iso(self.clock.now())
        r = await self._get("/cards/named", {"exact": name.strip()})
        if r.status_code == 200:
            card = self._to_card(r.json(), now)
            self._write_cache(key, {"fetched_at": now, "card": card.model_dump()})
            return CardLookup(query=name, card=card, provider=self.name)
        if r.status_code == 404:
            r2 = await self._get("/cards/named", {"fuzzy": name.strip()})
            if r2.status_code == 200:
                card = self._to_card(r2.json(), now)
                if card.name.lower() != name.strip().lower():
                    # fuzzy matched a different name: report it as a suggestion, not a silent substitution
                    self._write_cache(key, {"fetched_at": now, "ambiguous": [card.name]})
                    return CardLookup(query=name, ambiguous=[card.name], provider=self.name)
                self._write_cache(key, {"fetched_at": now, "card": card.model_dump()})
                return CardLookup(query=name, card=card, provider=self.name)
            if r2.status_code == 404:
                detail = r2.json().get("details", "") if r2.headers.get("content-type", "").startswith("application/json") else ""
                # Scryfall lists candidate names in the 404 details for ambiguous fuzzy queries
                names = [n.strip() for n in detail.split(":")[-1].split(",")] if "ambiguous" in detail.lower() else []
                payload = {"fetched_at": now, "ambiguous": names} if names else {"fetched_at": now, "not_found": True}
                self._write_cache(key, payload)
                return CardLookup(query=name, ambiguous=names, not_found=not names, provider=self.name)
            raise UpstreamError(f"Scryfall returned {r2.status_code}")
        raise UpstreamError(f"Scryfall returned {r.status_code}: {r.text[:120]}")

    async def health(self) -> DependencyStatus:
        try:
            r = await self._get("/cards/named", {"exact": "Sol Ring"})
            return DependencyStatus(name="mtg", status="ok" if r.status_code == 200 else "degraded", detail=f"Scryfall {r.status_code}")
        except (UpstreamError, UpstreamUnavailable) as exc:
            return DependencyStatus(name="mtg", status="down", detail=exc.message[:160])
