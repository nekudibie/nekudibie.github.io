from __future__ import annotations

from typing import Protocol

from companion_contracts.health import DependencyStatus
from pydantic import BaseModel, ConfigDict, Field

# WMO weather interpretation codes (WW), as used by Open-Meteo's weather_code variable.
WMO_CODES: dict[int, str] = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle", 56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain", 66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains", 80: "slight rain showers", 81: "moderate rain showers",
    82: "violent rain showers", 85: "slight snow showers", 86: "heavy snow showers", 95: "thunderstorm", 96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class DayForecast(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    weather_code: int | None = None
    description: str = ""
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability_pct: int | None = None
    wind_max_kmh: float | None = None


class Forecast(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_name: str
    latitude: float
    longitude: float
    timezone: str
    days: list[DayForecast] = Field(default_factory=list)
    fetched_at: str
    is_stale: bool = False
    stale_reason: str | None = None
    provider: str
    is_fixture: bool = False
    attribution: str = ""


class WeatherProvider(Protocol):
    name: str
    is_fixture: bool

    async def forecast(self, *, force_refresh: bool = False) -> Forecast: ...
    async def health(self) -> DependencyStatus: ...


def describe(code: int | None) -> str:
    if code is None:
        return "unknown"
    return WMO_CODES.get(code, f"weather code {code}")
