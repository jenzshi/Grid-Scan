"""GET /api/ercot/history — survival analysis for current conditions."""

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.data.ercot_client import get_current_load, get_thermal_outages
from backend.analysis.forecast_error import calculate_error
from backend.analysis.historical_analysis import build_history_response

router = APIRouter(prefix="/api/ercot", tags=["history"])


@router.get("/history")
def get_history():
    """Return survival analysis for current conditions."""
    load = get_current_load()
    outages = get_thermal_outages()
    error = calculate_error(load["forecast_mw"], load["actual_mw"])

    current = _build_current_conditions(load, outages, error)
    return build_history_response(current)


def _build_current_conditions(load: dict, outages: dict, error: dict) -> dict:
    """
    Build conditions dict for the survival analysis engine.

    Args:
        load: Current load data.
        outages: Current thermal outage data.
        error: Calculated forecast error.

    Returns:
        Dict with keys matching historical period fields.
    """
    month = datetime.now(timezone.utc).month
    if month in (6, 7, 8):
        season = "summer"
    elif month in (12, 1, 2):
        season = "winter"
    elif month in (3, 4, 5):
        season = "spring"
    else:
        season = "fall"

    return {
        "season": season,
        "peak_error_pct": abs(error["error_pct"]),
        "thermal_outage_mw": outages["thermal_outage_mw"],
        "pre_period_planned_outage_mw": 3500.0,
        "reserve_margin_pct": 0.12,
    }
