"""Tests for error_decomposer module."""

from backend.analysis.error_decomposer import (
    decompose_error,
    format_decomposition_summary,
)


def test_zero_error_returns_empty_components():
    """No error means nothing to decompose."""
    result = decompose_error(0.0, 100.0, 50.0, 200.0, 3.0)
    assert result["total_error_mw"] == 0.0
    assert result["components"] == []


def test_all_components_present():
    """When all sources contribute, all appear in components list."""
    result = decompose_error(
        total_error_mw=5000.0,
        wind_shortfall_mw=1000.0,
        solar_shortfall_mw=500.0,
        thermal_outage_delta_mw=800.0,
        weather_temp_delta_f=3.0,
    )
    keys = [c["key"] for c in result["components"]]
    assert "wind" in keys
    assert "solar" in keys
    assert "thermal" in keys
    assert "temperature" in keys


def test_components_sorted_by_mw_descending():
    """Largest component first."""
    result = decompose_error(
        total_error_mw=10000.0,
        wind_shortfall_mw=200.0,
        solar_shortfall_mw=100.0,
        thermal_outage_delta_mw=5000.0,
        weather_temp_delta_f=1.0,
    )
    mws = [c["mw"] for c in result["components"]]
    assert mws == sorted(mws, reverse=True)


def test_percentages_sum_to_100_or_less():
    """Component percentages should not exceed 100%."""
    result = decompose_error(3000.0, 1200.0, 400.0, 800.0, 3.0)
    total_pct = sum(c["pct"] for c in result["components"])
    assert total_pct <= 101.0  # allow rounding tolerance


def test_scaling_when_attributed_exceeds_total():
    """When attributed components exceed total error, scale down proportionally."""
    result = decompose_error(
        total_error_mw=1000.0,
        wind_shortfall_mw=800.0,
        solar_shortfall_mw=600.0,
        thermal_outage_delta_mw=500.0,
        weather_temp_delta_f=5.0,
    )
    assert result["unexplained_mw"] == 0.0
    component_sum = sum(c["mw"] for c in result["components"])
    assert abs(component_sum - 1000.0) < 1.0


def test_negative_shortfalls_ignored():
    """Negative shortfalls (over-performance) contribute zero."""
    result = decompose_error(
        total_error_mw=2000.0,
        wind_shortfall_mw=-500.0,
        solar_shortfall_mw=-200.0,
        thermal_outage_delta_mw=0.0,
        weather_temp_delta_f=0.0,
    )
    assert result["wind_shortfall_mw"] == 0.0
    assert result["solar_shortfall_mw"] == 0.0
    assert result["unexplained_mw"] == 2000.0


def test_cold_weather_no_temp_contribution():
    """When actual temp is below forecast, no temperature demand component."""
    result = decompose_error(
        total_error_mw=2000.0,
        wind_shortfall_mw=1000.0,
        solar_shortfall_mw=500.0,
        thermal_outage_delta_mw=0.0,
        weather_temp_delta_f=-3.0,
    )
    assert result["temperature_demand_mw"] == 0.0


def test_format_summary_returns_string():
    """Summary formatter produces a non-empty string."""
    decomp = decompose_error(3000.0, 1200.0, 400.0, 800.0, 3.0)
    summary = format_decomposition_summary(decomp)
    assert isinstance(summary, str)
    assert "MW" in summary


def test_format_summary_zero_error():
    """Zero error produces a no-error message."""
    decomp = decompose_error(0.0, 0.0, 0.0, 0.0, 0.0)
    summary = format_decomposition_summary(decomp)
    assert "No significant" in summary
