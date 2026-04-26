"""GET /api/ercot/live — current snapshot, active event, fingerprint match."""

from fastapi import APIRouter

from backend.data.ercot_client import (
    get_current_load,
    get_reserve_status,
    get_thermal_outages,
    get_wind_status,
    get_solar_status,
    get_fuel_mix,
)
from backend.data.weather_client import get_current_weather, get_forecast_weather
from backend.analysis.error_decomposer import (
    decompose_error,
    format_decomposition_summary,
)
from backend.analysis.forecast_error import (
    calculate_error,
    calculate_growth_rate,
    is_dangerous,
)
from backend.analysis.classifier import (
    classify_cause,
    classify_cause_v2,
    classify_supply_subcause,
)
from backend.analysis.metrics import (
    reserve_headroom_pct,
    prc_status,
    stress_score,
)
from backend.analysis.fingerprinter import fingerprint
from backend.config import HISTORICAL_FINGERPRINTS
from backend.storage.supabase_client import get_recent_snapshots

router = APIRouter(prefix="/api/ercot", tags=["live"])


@router.get("/live")
def get_live():
    """Return current grid conditions snapshot."""
    load = get_current_load()
    reserves = get_reserve_status()
    outages = get_thermal_outages()
    wind = get_wind_status()
    solar = get_solar_status()
    fuel_mix = get_fuel_mix()
    weather_now = get_current_weather()
    weather_forecast = get_forecast_weather()

    error = calculate_error(load["forecast_mw"], load["actual_mw"])

    snapshots = get_recent_snapshots(hours=4)
    growth_rate = calculate_growth_rate(snapshots) if snapshots else 0.0

    dangerous = is_dangerous(error["error_pct"], growth_rate)

    temp_delta = weather_now["temp_f"] - weather_forecast["temp_f"]
    thermal_outage_delta = outages["thermal_outage_mw"] - 3600.0

    cause = classify_cause(
        error_mw=error["error_mw"],
        thermal_outage_delta_mw=thermal_outage_delta,
        weather_temp_delta_f=temp_delta,
    )

    decomposition = decompose_error(
        total_error_mw=error["error_mw"],
        wind_shortfall_mw=wind["wind_shortfall_mw"],
        solar_shortfall_mw=solar["solar_shortfall_mw"],
        thermal_outage_delta_mw=max(thermal_outage_delta, 0),
        weather_temp_delta_f=temp_delta,
    )
    decomposition_summary = format_decomposition_summary(decomposition)

    # Enhanced classification using full decomposition
    cause_v2 = classify_cause_v2(decomposition)
    supply_subcause = classify_supply_subcause(decomposition)
    cause_description = _build_cause_description_v2(
        cause_v2, supply_subcause, decomposition, temp_delta,
    )

    prc_mw = reserves["physical_responsive_capability_mw"]
    prc_label = prc_status(prc_mw)
    reserve_pct = reserve_headroom_pct(
        reserves["reserve_margin_mw"], load["forecast_mw"]
    )
    score = stress_score(
        error["error_pct"],
        growth_rate,
        prc_mw,
        reserves["reserve_price_adder"],
    )

    recent_scores = _extract_sparkline_data(snapshots, score, "stress_score")
    recent_errors = _extract_sparkline_data(
        snapshots, abs(error["error_pct"]), "error_pct"
    )
    recent_timestamps = _extract_sparkline_timestamps(snapshots)

    # Fingerprint matching
    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).month
    if month in (6, 7, 8):
        season = "summer"
    elif month in (12, 1, 2):
        season = "winter"
    elif month in (3, 4, 5):
        season = "spring"
    else:
        season = "fall"

    fp_result = fingerprint({
        "season": season,
        "peak_error_pct": abs(error["error_pct"]),
        "thermal_outage_mw_peak": outages["thermal_outage_mw"],
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "wind_shortfall_mw": wind["wind_shortfall_mw"],
        "renewable_outage_mw_peak": wind["wind_shortfall_mw"] + solar["solar_shortfall_mw"],
    })

    score_timeseries = _build_score_timeseries(snapshots, score)

    fp_match = fp_result["match"]
    fp_detail = _get_fingerprint_narrative(fp_match)
    fp_key = _find_fingerprint_key(fp_match)

    return {
        "timestamp": load["timestamp"],
        "forecast_mw": load["forecast_mw"],
        "actual_mw": load["actual_mw"],
        "error_mw": error["error_mw"],
        "error_pct": error["error_pct"],
        "growth_rate_mw_per_hour": growth_rate,
        "is_dangerous": dangerous,
        "cause": cause_v2,
        "cause_description": cause_description,
        "supply_subcause": supply_subcause,
        "reserve_margin_mw": reserves["reserve_margin_mw"],
        "reserve_margin_pct": reserve_pct,
        "prc_mw": prc_mw,
        "prc_status": prc_label,
        "thermal_outage_mw": outages["thermal_outage_mw"],
        "reserve_price_adder": reserves["reserve_price_adder"],
        "weather_temp_f": weather_now["temp_f"],
        "stress_score": score,
        "recent_scores": recent_scores,
        "recent_errors": recent_errors,
        "recent_timestamps": recent_timestamps,
        "fingerprint_match": fp_match,
        "fingerprint_similarity": fp_result["similarity"],
        "fingerprint_detail": fp_detail,
        "fingerprint_key": fp_key,
        "score_timeseries": score_timeseries,
        "wind_actual_mw": wind["wind_actual_mw"],
        "wind_forecast_mw": wind["wind_forecast_mw"],
        "wind_shortfall_mw": wind["wind_shortfall_mw"],
        "solar_actual_mw": solar["solar_actual_mw"],
        "solar_forecast_mw": solar["solar_forecast_mw"],
        "solar_shortfall_mw": solar["solar_shortfall_mw"],
        "error_decomposition": decomposition,
        "decomposition_summary": decomposition_summary,
        "fuel_mix": fuel_mix,
    }


def _build_cause_description_v2(
    cause: str,
    subcause: str | None,
    decomposition: dict,
    temp_delta: float,
) -> str:
    """
    Build a rich plain-English cause sentence using full decomposition.

    Args:
        cause: V2 classification result.
        subcause: Supply subcause or None.
        decomposition: Full error decomposition dict.
        temp_delta: Actual minus forecast temperature.

    Returns:
        Human-readable cause description.
    """
    if cause == "demand_side":
        return (
            f"Currently: Demand-Side — temperature exceeded forecast by "
            f"{abs(temp_delta):.0f}\u00b0F driving load above projections."
        )
    if cause == "supply_side":
        return _supply_description(subcause, decomposition)
    if cause == "mixed":
        return _mixed_description(decomposition, temp_delta)
    return "Currently: No significant divergence detected."


def _supply_description(subcause: str | None, decomposition: dict) -> str:
    """
    Build supply-side cause description with subcause detail.

    Args:
        subcause: Specific supply subcause string.
        decomposition: Full error decomposition dict.

    Returns:
        Human-readable supply-side description.
    """
    labels = {
        "thermal_trip": "thermal generator trips",
        "wind_shortfall": "wind generation underperforming forecast",
        "solar_ramp": "solar output below forecast",
        "combined_renewable": "combined wind and solar shortfall",
    }
    detail = labels.get(subcause, "supply-side generation shortfall")
    wind = decomposition.get("wind_shortfall_mw", 0)
    thermal = decomposition.get("thermal_outage_impact_mw", 0)

    parts = []
    if thermal >= 100:
        parts.append(f"{thermal:,.0f} MW thermal outages")
    if wind >= 100:
        parts.append(f"{wind:,.0f} MW wind shortfall")

    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"Currently: Supply-Side — {detail}{suffix}."


def _mixed_description(decomposition: dict, temp_delta: float) -> str:
    """
    Build mixed cause description showing both supply and demand factors.

    Args:
        decomposition: Full error decomposition dict.
        temp_delta: Actual minus forecast temperature.

    Returns:
        Human-readable mixed cause description.
    """
    temp_mw = decomposition.get("temperature_demand_mw", 0)
    wind = decomposition.get("wind_shortfall_mw", 0)
    thermal = decomposition.get("thermal_outage_impact_mw", 0)
    supply_total = wind + thermal + decomposition.get("solar_shortfall_mw", 0)

    return (
        f"Currently: Mixed — temperature surprise (+{abs(temp_delta):.0f}\u00b0F, "
        f"~{temp_mw:,.0f} MW demand) combined with {supply_total:,.0f} MW "
        f"supply-side shortfall."
    )


def _extract_sparkline_data(
    snapshots: list[dict], current_value: float, field: str
) -> list[float]:
    """
    Extract a time-series from recent snapshots, appending the current value.

    Args:
        snapshots: Recent snapshot dicts from Supabase.
        current_value: The latest computed value to append.
        field: Key to extract from each snapshot.

    Returns:
        List of floats for sparkline rendering.
    """
    values = []
    for snap in snapshots:
        val = snap.get(field)
        if val is not None:
            values.append(abs(val) if field == "error_pct" else val)
    values.append(current_value)
    return values


def _extract_sparkline_timestamps(snapshots: list[dict]) -> list[str]:
    """
    Extract ISO timestamp strings from snapshots for sparkline x-axis.

    Args:
        snapshots: Recent snapshot dicts with captured_at.

    Returns:
        List of ISO timestamp strings plus 'now' for the current point.
    """
    from datetime import datetime, timezone

    timestamps = []
    for snap in snapshots:
        ts = snap.get("captured_at", "")
        if ts:
            timestamps.append(ts[:19])
    timestamps.append(datetime.now(timezone.utc).isoformat()[:19])
    return timestamps


def _build_score_timeseries(
    snapshots: list[dict], current_score: float
) -> dict:
    """
    Build a time-keyed dict of stress scores for the line chart.

    Args:
        snapshots: Recent snapshot dicts with captured_at and stress_score.
        current_score: The current computed stress score.

    Returns:
        Dict mapping ISO timestamp keys to score values.
    """
    from datetime import datetime, timezone

    series = {}
    for snap in snapshots:
        ts = snap.get("captured_at", "")
        score = snap.get("stress_score")
        if ts and score is not None:
            key = ts[:19]
            series[key] = round(score, 1)

    now_key = datetime.now(timezone.utc).isoformat()[:19]
    series[now_key] = round(current_score, 1)
    return series


def _get_fingerprint_narrative(match_label: str | None) -> dict | None:
    """
    Look up a matched fingerprint label and return narrative context.

    Args:
        match_label: The label string from fingerprint matching.

    Returns:
        Dict with label, notes, outcome, cause, load_shed_mw,
        customers_affected, eea_level_reached — or None if no match.
    """
    if not match_label:
        return None

    for fp in HISTORICAL_FINGERPRINTS.values():
        if fp.get("label") == match_label:
            return {
                "label": fp["label"],
                "notes": fp.get("notes"),
                "outcome": fp.get("outcome"),
                "cause": fp.get("cause"),
                "load_shed_mw": fp.get("load_shed_mw"),
                "customers_affected": fp.get("customers_affected"),
                "eea_level_reached": fp.get("eea_level_reached"),
            }
    return None


def _find_fingerprint_key(match_label: str | None) -> str | None:
    """
    Find the config dict key for a matched fingerprint label.

    Args:
        match_label: The label string from fingerprint matching.

    Returns:
        The key string (e.g. 'uri_feb_2021') or None.
    """
    if not match_label:
        return None

    for key, fp in HISTORICAL_FINGERPRINTS.items():
        if fp.get("label") == match_label:
            return key
    return None
