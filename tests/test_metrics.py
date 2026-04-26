"""Tests for backend.analysis.metrics."""

from backend.analysis.metrics import reserve_headroom_pct, prc_status, stress_score


def test_reserve_headroom_pct_calculates_correctly():
    """Reserve headroom is reserve / forecast."""
    result = reserve_headroom_pct(7000.0, 70000.0)
    assert result == 0.1


def test_prc_status_returns_correct_labels():
    """PRC status matches threshold-based labels."""
    assert prc_status(7000.0) == "normal"
    assert prc_status(5000.0) == "watch"
    assert prc_status(2000.0) == "critical"


def test_stress_score_returns_0_to_100():
    """Stress score is bounded between 0 and 100."""
    low = stress_score(0.01, 100.0, 9000.0, 5.0)
    high = stress_score(0.25, 2500.0, 1000.0, 150.0)
    assert 0 <= low <= 100
    assert 0 <= high <= 100
    assert high > low
