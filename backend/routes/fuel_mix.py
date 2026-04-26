"""GET /api/ercot/fuel-mix — current generation by fuel type."""

from fastapi import APIRouter

from backend.data.ercot_client import get_fuel_mix
from backend.exceptions import ERCOTFetchError

router = APIRouter(prefix="/api/ercot", tags=["fuel-mix"])


@router.get("/fuel-mix")
def get_fuel_mix_route():
    """
    Return current ERCOT generation breakdown by fuel type.

    Returns:
        Dict with per-fuel MW values and total.
    """
    try:
        mix = get_fuel_mix()
    except ERCOTFetchError:
        mix = _empty_mix()

    total = sum(mix.values())
    percentages = _compute_percentages(mix, total)

    return {
        "generation": mix,
        "total_mw": round(total, 1),
        "percentages": percentages,
    }


def _compute_percentages(mix: dict, total: float) -> dict:
    """
    Convert MW values to percentages of total generation.

    Args:
        mix: Dict of fuel type to MW values.
        total: Total generation in MW.

    Returns:
        Dict of fuel type to percentage (0-100).
    """
    if total <= 0:
        return {k: 0.0 for k in mix}
    return {k: round((v / total) * 100, 1) for k, v in mix.items()}


def _empty_mix() -> dict:
    """Return zeroed fuel mix for error fallback."""
    return {
        "gas_mw": 0.0,
        "coal_mw": 0.0,
        "nuclear_mw": 0.0,
        "wind_mw": 0.0,
        "solar_mw": 0.0,
        "storage_mw": 0.0,
        "other_mw": 0.0,
    }
