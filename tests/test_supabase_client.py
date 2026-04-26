"""Tests for backend.storage.supabase_client (mock mode)."""

import uuid
from datetime import datetime, timezone, timedelta

from backend.storage.supabase_client import (
    save_snapshot,
    save_event,
    get_recent_snapshots,
    get_events,
    get_event_by_id,
    get_trend_aggregates,
    save_historical_period,
    get_historical_periods,
    historical_archive_exists,
)
from tests.conftest import mock_snapshot, mock_event, mock_historical_period


def test_save_and_get_snapshot():
    """Saving a snapshot makes it retrievable."""
    snap = mock_snapshot()
    save_snapshot(snap)
    results = get_recent_snapshots(hours=1)
    assert len(results) == 1
    assert results[0]["forecast_mw"] == snap["forecast_mw"]


def test_get_recent_snapshots_respects_hours():
    """Only snapshots within the time window are returned."""
    recent = mock_snapshot(minutes_ago=10)
    old = mock_snapshot(minutes_ago=180)
    save_snapshot(recent)
    save_snapshot(old)
    results = get_recent_snapshots(hours=1)
    assert len(results) == 1


def test_save_and_get_events():
    """Events are saved and returned with correct pagination."""
    for i in range(5):
        event = mock_event(peak_error_mw=1000.0 + i * 500)
        event["id"] = str(uuid.uuid4())
        save_event(event)
    all_events = get_events(limit=50)
    assert len(all_events) == 5
    page = get_events(limit=2, offset=0)
    assert len(page) == 2


def test_get_event_by_id_returns_correct_event():
    """Retrieving by ID returns the matching event."""
    event = mock_event()
    event["id"] = "test-event-123"
    save_event(event)
    result = get_event_by_id("test-event-123")
    assert result is not None
    assert result["id"] == "test-event-123"


def test_get_event_by_id_returns_none_for_missing():
    """Missing ID returns None."""
    result = get_event_by_id("nonexistent")
    assert result is None


def test_trend_aggregates_returns_expected_keys():
    """Trend aggregates contain the required top-level keys."""
    event = mock_event()
    event["id"] = str(uuid.uuid4())
    event["detected_at"] = "2024-07-15T14:00:00+00:00"
    save_event(event)
    agg = get_trend_aggregates()
    assert "monthly_events" in agg
    assert "avg_response_lag_by_month" in agg
    assert "cause_breakdown" in agg


def test_historical_period_save_and_retrieve():
    """Historical periods can be saved and filtered by season."""
    save_historical_period(mock_historical_period(year=2020, season="summer"))
    save_historical_period(mock_historical_period(year=2021, season="winter"))
    all_periods = get_historical_periods()
    assert len(all_periods) == 2
    summer = get_historical_periods(season="summer")
    assert len(summer) == 1
    assert summer[0]["season"] == "summer"


def test_historical_archive_exists():
    """Archive existence check works."""
    assert historical_archive_exists() is False
    save_historical_period(mock_historical_period())
    assert historical_archive_exists() is True
