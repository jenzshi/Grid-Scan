"""GET /api/ercot/fingerprint — current fingerprint match only."""

from fastapi import APIRouter

from backend.data.ercot_client import get_current_load, get_thermal_outages
from backend.analysis.forecast_error import calculate_error
from backend.analysis.fingerprinter import fingerprint

router = APIRouter(prefix="/api/ercot", tags=["fingerprint"])


@router.get("/fingerprint")
def get_fingerprint():
    """Return the best historical fingerprint match for current conditions."""
    load = get_current_load()
    outages = get_thermal_outages()
    error = calculate_error(load["forecast_mw"], load["actual_mw"])

    current = _build_current_conditions(load, outages, error)
    result = fingerprint(current)

    return {
        "match": result["match"],
        "similarity": result["similarity"],
        "conditions": current,
    }


def _build_current_conditions(load: dict, outages: dict, error: dict) -> dict:
    """
    Build a conditions dict from live data for the fingerprinter.

    Args:
        load: Current load data.
        outages: Current thermal outage data.
        error: Calculated error dict.

    Returns:
        Dict suitable for fingerprint().
    """
    # Determine season from current month
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

    return {
        "season": season,
        "peak_error_pct": abs(error["error_pct"]),
        "thermal_outage_mw_peak": outages["thermal_outage_mw"],
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
    }
