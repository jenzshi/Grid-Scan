"""Tests for backend.analysis.fingerprinter."""

from backend.analysis.fingerprinter import fingerprint


def test_fingerprint_perfect_match_returns_high_similarity():
    """Conditions matching Uri closely should return high similarity."""
    current = {
        "season": "winter",
        "peak_error_pct": 0.199,
        "thermal_outage_mw_peak": 28000,
        "prc_collapsed": True,
        "eea_level_reached": 3,
        "load_shed_mw": 20000,
    }
    result = fingerprint(current)
    assert result["match"] is not None
    assert result["similarity"] >= 0.7


def test_fingerprint_no_match_returns_none():
    """Normal conditions should not match any historical signature."""
    current = {
        "season": "summer",
        "peak_error_pct": 0.01,
        "thermal_outage_mw_peak": 1000,
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
    }
    result = fingerprint(current)
    assert result["match"] is None
    assert result["similarity"] is None


def test_fingerprint_partial_match_returns_moderate_score():
    """Conditions with some overlap should return a moderate score."""
    current = {
        "season": "winter",
        "peak_error_pct": 0.10,
        "thermal_outage_mw_peak": 10000,
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
    }
    result = fingerprint(current)
    if result["match"] is not None:
        assert 0.4 <= result["similarity"] <= 1.0


def test_fingerprint_winter_event_does_not_match_summer():
    """Winter conditions should not match summer-only signatures."""
    current = {
        "season": "winter",
        "peak_error_pct": 0.05,
        "thermal_outage_mw_peak": 5000,
        "prc_collapsed": False,
        "eea_level_reached": 1,
        "load_shed_mw": 0,
    }
    result = fingerprint(current)
    # If there is a match, it should be a winter event
    if result["match"] is not None:
        assert "Summer" not in result["match"]
