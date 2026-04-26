"""Break total forecast error into attributed root cause components."""

# Approximate MW of additional demand per degree F of temperature surprise.
# Based on ERCOT load sensitivity: ~500-700 MW per degree during summer peaks.
_MW_PER_DEGREE_F = 600.0


def decompose_error(
    total_error_mw: float,
    wind_shortfall_mw: float,
    solar_shortfall_mw: float,
    thermal_outage_delta_mw: float,
    weather_temp_delta_f: float,
) -> dict:
    """
    Break total forecast error into attributed components.

    Supply-side components (wind, solar, thermal) are direct MW values.
    Demand-side temperature component is estimated from temp delta.
    Unexplained residual captures anything not attributable.

    Args:
        total_error_mw: Actual minus forecast demand in MW.
        wind_shortfall_mw: Wind forecast minus actual generation.
        solar_shortfall_mw: Solar forecast minus actual generation.
        thermal_outage_delta_mw: Thermal outages above normal baseline.
        weather_temp_delta_f: Actual temp minus forecast temp.

    Returns:
        Dict with per-component MW, percentages, and a components list.
    """
    abs_error = abs(total_error_mw)
    if abs_error < 1.0:
        return _zero_decomposition()

    wind_contrib = max(wind_shortfall_mw, 0.0)
    solar_contrib = max(solar_shortfall_mw, 0.0)
    thermal_contrib = max(thermal_outage_delta_mw, 0.0)
    temp_contrib = _estimate_temperature_demand(weather_temp_delta_f)

    attributed = wind_contrib + solar_contrib + thermal_contrib + temp_contrib
    unexplained = max(abs_error - attributed, 0.0)

    # If attributed exceeds total error, scale components proportionally
    if attributed > abs_error and attributed > 0:
        scale = abs_error / attributed
        wind_contrib = round(wind_contrib * scale, 1)
        solar_contrib = round(solar_contrib * scale, 1)
        thermal_contrib = round(thermal_contrib * scale, 1)
        temp_contrib = round(temp_contrib * scale, 1)
        unexplained = 0.0

    components = _build_components_list(
        abs_error, wind_contrib, solar_contrib,
        thermal_contrib, temp_contrib, unexplained,
    )

    return {
        "total_error_mw": round(abs_error, 1),
        "wind_shortfall_mw": round(wind_contrib, 1),
        "solar_shortfall_mw": round(solar_contrib, 1),
        "thermal_outage_impact_mw": round(thermal_contrib, 1),
        "temperature_demand_mw": round(temp_contrib, 1),
        "unexplained_mw": round(unexplained, 1),
        "components": components,
    }


def format_decomposition_summary(decomposition: dict) -> str:
    """
    Build a plain-English summary of the error decomposition.

    Args:
        decomposition: Output dict from decompose_error.

    Returns:
        One-sentence human-readable breakdown.
    """
    total = decomposition["total_error_mw"]
    if total < 1.0:
        return "No significant forecast error to decompose."

    parts = []
    for comp in decomposition["components"]:
        if comp["mw"] >= 1.0 and comp["key"] != "unexplained":
            parts.append(f"{comp['label']}: {comp['mw']:,.0f} MW ({comp['pct']:.0f}%)")

    if not parts:
        return f"Forecast error of {total:,.0f} MW with no clear attribution."

    joined = ", ".join(parts)
    return f"Error breakdown — {joined}."


def _estimate_temperature_demand(temp_delta_f: float) -> float:
    """
    Estimate additional MW demand from temperature surprise.

    Args:
        temp_delta_f: Actual minus forecast temperature in Fahrenheit.

    Returns:
        Estimated additional demand in MW (zero if temp was cooler).
    """
    if temp_delta_f <= 0:
        return 0.0
    return temp_delta_f * _MW_PER_DEGREE_F


def _zero_decomposition() -> dict:
    """Return a zeroed decomposition when error is negligible."""
    return {
        "total_error_mw": 0.0,
        "wind_shortfall_mw": 0.0,
        "solar_shortfall_mw": 0.0,
        "thermal_outage_impact_mw": 0.0,
        "temperature_demand_mw": 0.0,
        "unexplained_mw": 0.0,
        "components": [],
    }


def _build_components_list(
    total_mw: float,
    wind_mw: float,
    solar_mw: float,
    thermal_mw: float,
    temp_mw: float,
    unexplained_mw: float,
) -> list[dict]:
    """
    Build a sorted list of component dicts for frontend rendering.

    Args:
        total_mw: Absolute total error.
        wind_mw: Wind shortfall contribution.
        solar_mw: Solar shortfall contribution.
        thermal_mw: Thermal outage contribution.
        temp_mw: Temperature demand contribution.
        unexplained_mw: Residual not attributed.

    Returns:
        List of dicts with key, label, mw, pct, color — sorted descending.
    """
    raw = [
        ("wind", "Wind Shortfall", wind_mw, "#1d4ed8"),
        ("solar", "Solar Shortfall", solar_mw, "#d97706"),
        ("thermal", "Thermal Outages", thermal_mw, "#b91c1c"),
        ("temperature", "Temperature Demand", temp_mw, "#ea580c"),
        ("unexplained", "Unexplained", unexplained_mw, "#94a3b8"),
    ]

    components = []
    for key, label, mw, color in raw:
        if mw < 1.0:
            continue
        pct = (mw / total_mw) * 100.0 if total_mw > 0 else 0.0
        components.append({
            "key": key,
            "label": label,
            "mw": round(mw, 1),
            "pct": round(pct, 1),
            "color": color,
        })

    components.sort(key=lambda c: c["mw"], reverse=True)
    return components
