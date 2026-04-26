"""Weather data fetching from Open-Meteo. Mock mode returns hot afternoon."""

import logging

import httpx

from backend.config import MOCK_MODE
from backend.exceptions import WeatherFetchError

logger = logging.getLogger(__name__)

# Dallas, TX coordinates — proxy for ERCOT load center
_DALLAS_LAT = 32.78
_DALLAS_LON = -96.80
_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_current_weather() -> dict:
    """Fetch current Dallas-area temperature as grid proxy."""
    if MOCK_MODE:
        return _mock_current_weather()
    try:
        return _live_current_weather()
    except Exception as exc:
        raise WeatherFetchError(
            f"Failed to fetch weather data: {exc}"
        ) from exc


def get_forecast_weather() -> dict:
    """Fetch forecast temperature for comparison to actual."""
    if MOCK_MODE:
        return _mock_forecast_weather()
    try:
        return _live_forecast_weather()
    except Exception as exc:
        raise WeatherFetchError(
            f"Failed to fetch forecast weather: {exc}"
        ) from exc


def _live_current_weather() -> dict:
    """Fetch current temperature from Open-Meteo."""
    resp = httpx.get(
        _OPEN_METEO_URL,
        params={
            "latitude": _DALLAS_LAT,
            "longitude": _DALLAS_LON,
            "current_weather": "true",
            "temperature_unit": "fahrenheit",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    temp_f = data.get("current_weather", {}).get("temperature", 0)
    return {
        "temp_f": round(float(temp_f), 1),
        "location": "Dallas, TX",
    }


def _live_forecast_weather() -> dict:
    """
    Fetch today's forecast high from Open-Meteo.

    Uses the daily max temperature as the forecast baseline
    to compare against the actual current temperature.
    """
    resp = httpx.get(
        _OPEN_METEO_URL,
        params={
            "latitude": _DALLAS_LAT,
            "longitude": _DALLAS_LON,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "forecast_days": "1",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily", {})
    temps = daily.get("temperature_2m_max", [])
    forecast_temp = temps[0] if temps else 0

    return {
        "temp_f": round(float(forecast_temp), 1),
        "location": "Dallas, TX",
    }


def _mock_current_weather() -> dict:
    """Simulate a hot summer afternoon in Dallas."""
    return {"temp_f": 98.0, "location": "Dallas, TX"}


def _mock_forecast_weather() -> dict:
    """Simulate a forecast that underestimated heat."""
    return {"temp_f": 95.0, "location": "Dallas, TX"}
