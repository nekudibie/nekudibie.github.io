"""Open-Meteo forecast adapter (docs/SOURCES.md).

``GET https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&daily=...&timezone=...``
returns ``daily.time[]`` plus one array per requested variable. Free for non-commercial use,
no API key, data CC BY 4.0: the UI shows the required attribution link. Results are cached on
disk with their fetch time; when a refresh fails the cached forecast is returned and labelled stale.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from companion_contracts.health import DependencyStatus
from companion_core.clock import Clock, SystemClock, iso, parse_iso
from companion_core.errors import NotConfigured, UpstreamError, UpstreamUnavailable
from companion_core.logging import get_logger

from .base import DayForecast, Forecast, describe

log = get_logger(__name__)
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
DAILY_VARS = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max"


class OpenMeteoProvider:
    name = "open_meteo"
    is_fixture = False

    def __init__(self, latitude: float, longitude: float, *, location_name: str = "", timezone: str = "Europe/London", cache_path: Path | None = None,
                 cache_ttl_s: int = 1800, timeout_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None, clock: Clock | None = None,
                 base_url: str = "https://api.open-meteo.com") -> None:
        self.latitude, self.longitude = latitude, longitude
        self.location_name = location_name or f"{latitude:.3f}, {longitude:.3f}"
        self.timezone = timezone
        self.cache_path = cache_path
        self.cache_ttl_s = cache_ttl_s
        self.clock = clock or SystemClock()
        self._client = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(connect=3.0, read=timeout_s, write=timeout_s, pool=3.0), transport=transport,
                                         headers={"User-Agent": "NekuDeskCompanion/0.1 (personal, local-first)"})
        self._mem: Forecast | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    def _load_cache(self) -> Forecast | None:
        if self._mem is not None:
            return self._mem
        if self.cache_path and self.cache_path.is_file():
            try:
                self._mem = Forecast.model_validate_json(self.cache_path.read_text(encoding="utf-8"))
            except ValueError:
                return None
        return self._mem

    def _save_cache(self, fc: Forecast) -> None:
        self._mem = fc
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(fc.model_dump_json(), encoding="utf-8")

    def _fresh(self, fc: Forecast) -> bool:
        return (self.clock.now() - parse_iso(fc.fetched_at)).total_seconds() < self.cache_ttl_s

    async def forecast(self, *, force_refresh: bool = False) -> Forecast:
        cached = self._load_cache()
        if cached and not force_refresh and self._fresh(cached):
            return cached.model_copy(update={"is_stale": False, "stale_reason": None})
        try:
            fc = await self._fetch()
            self._save_cache(fc)
            return fc
        except (UpstreamUnavailable, UpstreamError) as exc:
            if cached:
                age_min = int((self.clock.now() - parse_iso(cached.fetched_at)).total_seconds() // 60)
                return cached.model_copy(update={"is_stale": True, "stale_reason": f"showing data fetched {age_min} min ago: {exc.message}"})
            raise

    async def _fetch(self) -> Forecast:
        params = {"latitude": self.latitude, "longitude": self.longitude, "daily": DAILY_VARS, "timezone": self.timezone, "forecast_days": 7}
        started = time.monotonic()
        try:
            r = await self._client.get("/v1/forecast", params=params)
        except httpx.TimeoutException as exc:
            raise UpstreamUnavailable("Open-Meteo timed out") from exc
        except httpx.TransportError as exc:
            raise UpstreamUnavailable(f"Open-Meteo unreachable ({exc.__class__.__name__})") from exc
        if r.status_code != 200:
            raise UpstreamError(f"Open-Meteo returned {r.status_code}: {r.text[:160]}")
        data = r.json()
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        days = []
        for i, date in enumerate(times):
            def pick(key: str, i: int = i):  # type: ignore[no-untyped-def]
                arr = daily.get(key) or []
                return arr[i] if i < len(arr) else None
            code = pick("weather_code")
            days.append(DayForecast(
                date=date, weather_code=code, description=describe(code), temp_max_c=pick("temperature_2m_max"), temp_min_c=pick("temperature_2m_min"),
                precipitation_mm=pick("precipitation_sum"), precipitation_probability_pct=pick("precipitation_probability_max"), wind_max_kmh=pick("wind_speed_10m_max"),
            ))
        log.info("weather fetched", extra={"ms": int((time.monotonic() - started) * 1000), "days": len(days)})
        return Forecast(location_name=self.location_name, latitude=self.latitude, longitude=self.longitude, timezone=data.get("timezone", self.timezone), days=days,
                        fetched_at=iso(self.clock.now()), provider=self.name, attribution=ATTRIBUTION)

    async def health(self) -> DependencyStatus:
        cached = self._load_cache()
        if cached and self._fresh(cached):
            return DependencyStatus(name="weather", status="ok", detail=f"Open-Meteo cache fresh ({cached.fetched_at})")
        try:
            await self._fetch()
            return DependencyStatus(name="weather", status="ok", detail="Open-Meteo reachable")
        except (UpstreamUnavailable, UpstreamError) as exc:
            return DependencyStatus(name="weather", status="degraded" if cached else "down", detail=exc.message[:160])


def build_open_meteo(cfg, *, clock: Clock | None = None):  # type: ignore[no-untyped-def]
    if cfg.weather.latitude is None or cfg.weather.longitude is None:
        raise NotConfigured("weather.latitude and weather.longitude are required for open_meteo")
    return OpenMeteoProvider(cfg.weather.latitude, cfg.weather.longitude, location_name=cfg.weather.location_name, timezone=cfg.instance.timezone,
                             cache_path=cfg.data_dir / "cache" / "weather.json", cache_ttl_s=cfg.weather.cache_ttl_s, timeout_s=cfg.weather.timeout_s, clock=clock)
