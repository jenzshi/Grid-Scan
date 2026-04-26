"""Tests for backend.analysis.classifier."""

from backend.analysis.classifier import classify_cause


def test_classify_high_outage_delta_returns_supply_side():
    """High thermal outage delta with low temp delta is supply-side."""
    result = classify_cause(
        error_mw=3000.0,
        thermal_outage_delta_mw=2000.0,
        weather_temp_delta_f=2.0,
    )
    assert result == "supply_side"


def test_classify_high_temp_delta_returns_demand_side():
    """High temp delta with low outage delta is demand-side."""
    result = classify_cause(
        error_mw=3000.0,
        thermal_outage_delta_mw=500.0,
        weather_temp_delta_f=8.0,
    )
    assert result == "demand_side"


def test_classify_both_elevated_returns_dominant():
    """When both signals are elevated, returns the dominant one."""
    result = classify_cause(
        error_mw=3000.0,
        thermal_outage_delta_mw=3000.0,
        weather_temp_delta_f=6.0,
    )
    assert result == "supply_side"


def test_classify_neutral_inputs_returns_undetermined():
    """Neither signal elevated returns undetermined."""
    result = classify_cause(
        error_mw=500.0,
        thermal_outage_delta_mw=200.0,
        weather_temp_delta_f=1.0,
    )
    assert result == "undetermined"
