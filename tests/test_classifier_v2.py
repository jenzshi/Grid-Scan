"""Tests for enhanced classifier (v2) and supply subcause."""

from backend.analysis.classifier import classify_cause_v2, classify_supply_subcause


def _make_decomp(wind=0.0, solar=0.0, thermal=0.0, temp=0.0, total=None):
    """Build a decomposition dict for testing."""
    if total is None:
        total = wind + solar + thermal + temp
    return {
        "total_error_mw": max(total, 0.1),
        "wind_shortfall_mw": wind,
        "solar_shortfall_mw": solar,
        "thermal_outage_impact_mw": thermal,
        "temperature_demand_mw": temp,
        "unexplained_mw": 0.0,
    }


def test_v2_demand_side():
    """Temperature-dominated error classifies as demand_side."""
    d = _make_decomp(wind=100, solar=50, thermal=0, temp=3000)
    assert classify_cause_v2(d) == "demand_side"


def test_v2_supply_side():
    """Supply-dominated error classifies as supply_side."""
    d = _make_decomp(wind=2000, solar=500, thermal=1000, temp=200)
    assert classify_cause_v2(d) == "supply_side"


def test_v2_mixed():
    """Balanced supply and demand signals classify as mixed."""
    d = _make_decomp(wind=1500, solar=0, thermal=0, temp=1800, total=3300)
    assert classify_cause_v2(d) == "mixed"


def test_v2_undetermined_zero_error():
    """Zero error returns undetermined."""
    d = _make_decomp(total=0.0)
    assert classify_cause_v2(d) == "undetermined"


def test_subcause_thermal_trip():
    """Thermal-dominated supply returns thermal_trip."""
    d = _make_decomp(wind=200, solar=100, thermal=3000)
    assert classify_supply_subcause(d) == "thermal_trip"


def test_subcause_wind_shortfall():
    """Wind-dominated supply returns wind_shortfall."""
    d = _make_decomp(wind=2000, solar=100, thermal=200)
    assert classify_supply_subcause(d) == "wind_shortfall"


def test_subcause_solar_ramp():
    """Solar-dominated supply returns solar_ramp."""
    d = _make_decomp(wind=100, solar=1500, thermal=200)
    assert classify_supply_subcause(d) == "solar_ramp"


def test_subcause_combined_renewable():
    """Both wind and solar significant returns combined_renewable."""
    d = _make_decomp(wind=1200, solar=800, thermal=100)
    assert classify_supply_subcause(d) == "combined_renewable"


def test_subcause_none_when_no_supply():
    """No significant supply component returns None."""
    d = _make_decomp(wind=10, solar=5, thermal=20, temp=3000)
    assert classify_supply_subcause(d) is None
