"""Tests for backend.analysis.forecast_error."""

from backend.analysis.forecast_error import (
    calculate_error,
    calculate_growth_rate,
    is_dangerous,
)


def test_calculate_error_zero():
    """Zero error when forecast equals actual."""
    result = calculate_error(70000.0, 70000.0)
    assert result["error_mw"] == 0.0
    assert result["error_pct"] == 0.0


def test_calculate_error_positive():
    """Positive error when actual exceeds forecast."""
    result = calculate_error(70000.0, 73500.0)
    assert result["error_mw"] == 3500.0
    assert result["error_pct"] == 0.05


def test_calculate_error_negative():
    """Negative error when actual is below forecast."""
    result = calculate_error(70000.0, 67000.0)
    assert result["error_mw"] == -3000.0
    assert result["error_pct"] < 0


def test_growth_rate_flat_snapshots():
    """Growth rate is zero when error is constant."""
    snapshots = [{"error_mw": 1000.0} for _ in range(6)]
    rate = calculate_growth_rate(snapshots)
    assert rate == 0.0


def test_growth_rate_rising_snapshots():
    """Growth rate is positive when error is increasing."""
    snapshots = [{"error_mw": 1000.0 + i * 100.0} for i in range(6)]
    rate = calculate_growth_rate(snapshots)
    assert rate > 0


def test_growth_rate_single_snapshot():
    """Growth rate is zero with only one snapshot."""
    rate = calculate_growth_rate([{"error_mw": 500.0}])
    assert rate == 0.0


def test_is_dangerous_below_both_thresholds():
    """Not dangerous when both values are below thresholds."""
    assert is_dangerous(0.03, 500.0) is False


def test_is_dangerous_error_pct_breaches():
    """Dangerous when error_pct alone exceeds threshold."""
    assert is_dangerous(0.06, 500.0) is True


def test_is_dangerous_growth_rate_breaches():
    """Dangerous when growth_rate alone exceeds threshold."""
    assert is_dangerous(0.03, 1200.0) is True
