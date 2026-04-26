"""Shared fixtures and mocks for all test modules."""

import pytest
from datetime import datetime, timezone, timedelta

from backend.storage import supabase_client


@pytest.fixture(autouse=True)
def reset_storage():
    """Reset the in-memory store before each test."""
    supabase_client._reset_store()
    yield
    supabase_client._reset_store()


def mock_snapshot(
    forecast_mw: float = 70000.0,
    actual_mw: float = 72000.0,
    minutes_ago: int = 0,
) -> dict:
    """Create a realistic grid snapshot for testing."""
    captured = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    error_mw = actual_mw - forecast_mw
    return {
        "captured_at": captured.isoformat(),
        "forecast_mw": forecast_mw,
        "actual_mw": actual_mw,
        "error_mw": error_mw,
        "error_pct": error_mw / forecast_mw if forecast_mw else 0,
        "reserve_margin_mw": 6000.0,
        "physical_responsive_capability_mw": 5800.0,
        "thermal_outage_mw": 3500.0,
        "reserve_price_adder": 15.0,
        "weather_temp_f": 98.0,
    }


def mock_event(
    cause: str = "demand_side",
    peak_error_mw: float = 3500.0,
    resolved: bool = False,
    fingerprint_match: str | None = None,
) -> dict:
    """Create a realistic stress event for testing."""
    detected = datetime.now(timezone.utc) - timedelta(hours=2)
    event = {
        "detected_at": detected.isoformat(),
        "resolved_at": (
            (detected + timedelta(hours=1)).isoformat() if resolved else None
        ),
        "cause": cause,
        "peak_error_mw": peak_error_mw,
        "peak_error_pct": peak_error_mw / 70000.0,
        "error_growth_rate_mw_per_hour": 800.0,
        "response_lag_minutes": 15,
        "response_adequate": True,
        "fingerprint_match": fingerprint_match,
        "fingerprint_similarity": 0.6 if fingerprint_match else None,
        "plain_summary": "Test event summary.",
        "raw_snapshot": {},
    }
    return event


def mock_historical_period(
    year: int = 2020,
    season: str = "summer",
    outcome: str = "normal",
) -> dict:
    """Create a historical period record for testing."""
    return {
        "period_start": f"{year}-07-01T00:00:00+00:00",
        "period_end": f"{year}-09-01T00:00:00+00:00",
        "season": season,
        "year": year,
        "peak_actual_mw": 75000.0,
        "peak_forecast_mw": 73000.0,
        "peak_error_mw": 2000.0,
        "peak_error_pct": 0.027,
        "max_thermal_outage_mw": 4000.0,
        "min_reserve_margin_pct": 0.12,
        "pre_period_planned_outage_mw": 3000.0,
        "cause_classification": "demand_side",
        "response_lag_minutes": None,
        "outcome": outcome,
        "outcome_source": "inferred",
        "notes": None,
    }
