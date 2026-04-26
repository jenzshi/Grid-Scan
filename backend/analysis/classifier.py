"""Demand-side vs supply-side cause classification."""

# Thresholds for classification
_OUTAGE_DELTA_SIGNIFICANT_MW = 1500.0
_TEMP_DELTA_SIGNIFICANT_F = 5.0


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
