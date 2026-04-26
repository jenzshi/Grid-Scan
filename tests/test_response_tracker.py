"""Tests for backend.analysis.response_tracker."""

from datetime import datetime, timezone, timedelta

from backend.analysis.response_tracker import find_response_time, assess_adequacy


def test_find_response_no_messages_returns_none():
    """No ops messages means no response found."""
    event_start = datetime(2024, 7, 15, 14, 0, tzinfo=timezone.utc)
    result = find_response_time(event_start, [])
    assert result is None


def test_find_response_message_before_event_ignored():
    """Messages before event_start should not count."""
    event_start = datetime(2024, 7, 15, 14, 0, tzinfo=timezone.utc)
    messages = [
        {
            "timestamp": (event_start - timedelta(hours=1)).isoformat(),
            "type": "conservation_appeal",
        },
    ]
    result = find_response_time(event_start, messages)
    assert result is None


def test_find_response_message_after_event_returns_lag():
    """Message after event_start returns correct lag in minutes."""
    event_start = datetime(2024, 7, 15, 14, 0, tzinfo=timezone.utc)
    messages = [
        {
            "timestamp": (event_start + timedelta(minutes=30)).isoformat(),
            "type": "conservation_appeal",
        },
    ]
    result = find_response_time(event_start, messages)
    assert result == 30


def test_assess_adequacy_slow_growth_fast_response():
    """Slow growth + fast response is adequate."""
    result = assess_adequacy(
        growth_rate_mw_per_hour=500.0,
        response_lag_minutes=15,
    )
    assert result is True


def test_assess_adequacy_fast_growth_slow_response():
    """Fast growth + slow response is inadequate."""
    result = assess_adequacy(
        growth_rate_mw_per_hour=5000.0,
        response_lag_minutes=120,
    )
    assert result is False
