"""Derived grid health metrics for the key metrics panel."""

from backend.config import GRIDS

_ERCOT = GRIDS["ERCOT"]


def reserve_headroom_pct(reserve_mw: float, forecast_mw: float) -> float:
    """
    Operating reserve as percentage of forecast demand.

    Args:
        reserve_mw: Current operating reserves in MW.
        forecast_mw: Current forecast demand in MW.

    Returns:
        Reserve headroom as a decimal fraction.
    """
    if forecast_mw <= 0:
        return 0.0
    result = reserve_mw / forecast_mw
    return round(result, 4)


def prc_status(prc_mw: float) -> str:
    """
    Classify PRC level as normal, watch, or critical.

    Args:
        prc_mw: Physical Responsive Capability in MW.

    Returns:
        'normal', 'watch', or 'critical'.
    """
    threshold = _ERCOT["prc_low_threshold_mw"]
    if prc_mw < threshold * 0.6:
        return "critical"
    if prc_mw < threshold:
        return "watch"
    return "normal"


def stress_score(
    error_pct: float,
    growth_rate: float,
    prc_mw: float,
    reserve_price_adder: float,
) -> float:
    """
    Composite 0-100 stress score. Higher means more stressed.

    Weighted combination of four inputs normalized to historical ranges.

    Args:
        error_pct: Forecast error as decimal fraction.
        growth_rate: Error growth rate in MW/hour.
        prc_mw: Physical Responsive Capability in MW.
        reserve_price_adder: ORDC price adder in $/MW.

    Returns:
        Score between 0 and 100.
    """
    # Normalize each component to 0-1 based on historical ranges
    error_norm = _clamp(abs(error_pct) / 0.20)
    growth_norm = _clamp(abs(growth_rate) / 2000.0)
    # PRC is inverted — lower PRC = higher stress
    prc_norm = _clamp(1.0 - (prc_mw / 10000.0))
    adder_norm = _clamp(reserve_price_adder / 100.0)

    # Weights: error and PRC matter most
    weighted = (
        error_norm * 0.30
        + growth_norm * 0.20
        + prc_norm * 0.30
        + adder_norm * 0.20
    )

    score = weighted * 100.0
    return round(min(max(score, 0.0), 100.0), 1)


def _clamp(value: float) -> float:
    """Clamp a value to the 0-1 range."""
    return min(max(value, 0.0), 1.0)
