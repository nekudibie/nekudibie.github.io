from __future__ import annotations

from datetime import timedelta

from companion_contracts.health import DependencyStatus
from companion_core.clock import Clock, SystemClock, iso

from .base import DayForecast, Forecast, describe


class FixtureWeatherProvider:
    name = "fixture"
    is_fixture = True

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    async def forecast(self, *, force_refresh: bool = False) -> Forecast:
        today = self.clock.now().date()
        codes = [3, 61, 2, 0, 80, 45, 1]
        days = [
            DayForecast(date=(today + timedelta(days=i)).isoformat(), weather_code=c, description=describe(c), temp_max_c=14 + i % 3, temp_min_c=7 + i % 2,
                        precipitation_mm=[0.2, 6.4, 0.0, 0.0, 3.1, 0.1, 0.0][i], precipitation_probability_pct=[20, 80, 10, 5, 60, 30, 10][i], wind_max_kmh=18.0 + i)
            for i, c in enumerate(codes)
        ]
        return Forecast(location_name="Fixture Town", latitude=0.0, longitude=0.0, timezone="Europe/London", days=days, fetched_at=iso(self.clock.now()),
                        provider=self.name, is_fixture=True, attribution="fixture data, not a real forecast")

    async def health(self) -> DependencyStatus:
        return DependencyStatus(name="weather", status="fixture", detail="fixture forecast: invented numbers")
