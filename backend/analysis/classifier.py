"""Demand-side vs supply-side cause classification."""

# Thresholds for classification
_OUTAGE_DELTA_SIGNIFICANT_MW = 1500.0
_TEMP_DELTA_SIGNIFICANT_F = 5.0
_WIND_SHORTFALL_SIGNIFICANT_MW = 1000.0
_SOLAR_SHORTFALL_SIGNIFICANT_MW = 500.0


def classify_cause(
    error_mw: float,
    thermal_outage_delta_mw: float,
    weather_temp_delta_f: float,
) -> str:
    """
    Classify whether forecast error is demand-side or supply-side.

    Supply-side: thermal outages increased significantly.
    Demand-side: temperature surprise drove load above forecast.
    Mixed: both factors present; returns the dominant one.

    Args:
        error_mw: Current forecast error in MW (actual - forecast).
        thermal_outage_delta_mw: Change in thermal outages (positive = more offline).
        weather_temp_delta_f: Actual temp minus forecast temp in Fahrenheit.

    Returns:
        'demand_side', 'supply_side', or 'undetermined'.
    """
    supply_signal = thermal_outage_delta_mw >= _OUTAGE_DELTA_SIGNIFICANT_MW
    demand_signal = weather_temp_delta_f >= _TEMP_DELTA_SIGNIFICANT_F

    if supply_signal and demand_signal:
        return _pick_dominant(thermal_outage_delta_mw, weather_temp_delta_f)
    if supply_signal:
        return "supply_side"
    if demand_signal:
        return "demand_side"
    return "undetermined"


def classify_cause_v2(decomposition: dict) -> str:
    """
    Multi-signal cause classification using full error decomposition.

    Uses all available signal components to determine whether the
    forecast error is demand-driven or supply-driven.

    Args:
        decomposition: Output dict from decompose_error.

    Returns:
        'supply_side', 'demand_side', 'mixed', or 'undetermined'.
    """
    supply_mw = _total_supply_contribution(decomposition)
    demand_mw = decomposition.get("temperature_demand_mw", 0.0)
    total = decomposition.get("total_error_mw", 0.0)

    if total < 1.0:
        return "undetermined"

    supply_pct = supply_mw / total
    demand_pct = demand_mw / total

    if supply_pct >= 0.6:
        return "supply_side"
    if demand_pct >= 0.6:
        return "demand_side"
    if supply_pct >= 0.3 and demand_pct >= 0.3:
        return "mixed"
    return "undetermined"


def classify_supply_subcause(decomposition: dict) -> str | None:
    """
    Identify the specific supply-side subcause from decomposition.

    Only meaningful when the primary cause is supply_side or mixed.

    Args:
        decomposition: Output dict from decompose_error.

    Returns:
        'thermal_trip', 'wind_shortfall', 'solar_ramp',
        'combined_renewable', or None if not supply-driven.
    """
    wind = decomposition.get("wind_shortfall_mw", 0.0)
    solar = decomposition.get("solar_shortfall_mw", 0.0)
    thermal = decomposition.get("thermal_outage_impact_mw", 0.0)

    supply_total = wind + solar + thermal
    if supply_total < 100.0:
        return None

    if thermal >= wind and thermal >= solar:
        return "thermal_trip"

    both_renewable = (
        wind >= _WIND_SHORTFALL_SIGNIFICANT_MW
        and solar >= _SOLAR_SHORTFALL_SIGNIFICANT_MW
    )
    if both_renewable:
        return "combined_renewable"

    if wind >= solar:
        return "wind_shortfall"
    return "solar_ramp"


def _total_supply_contribution(decomposition: dict) -> float:
    """
    Sum all supply-side components from a decomposition.

    Args:
        decomposition: Output dict from decompose_error.

    Returns:
        Total supply-side MW.
    """
    wind = decomposition.get("wind_shortfall_mw", 0.0)
    solar = decomposition.get("solar_shortfall_mw", 0.0)
    thermal = decomposition.get("thermal_outage_impact_mw", 0.0)
    return wind + solar + thermal


def _pick_dominant(
    thermal_outage_delta_mw: float,
    weather_temp_delta_f: float,
) -> str:
    """
    When both supply and demand signals are present, pick the dominant cause.

    Compares normalized magnitudes against their respective thresholds.

    Args:
        thermal_outage_delta_mw: Outage delta in MW.
        weather_temp_delta_f: Temperature delta in Fahrenheit.

    Returns:
        'supply_side' or 'demand_side'.
    """
    supply_ratio = thermal_outage_delta_mw / _OUTAGE_DELTA_SIGNIFICANT_MW
    demand_ratio = weather_temp_delta_f / _TEMP_DELTA_SIGNIFICANT_F

    if supply_ratio >= demand_ratio:
        return "supply_side"
    return "demand_side"
