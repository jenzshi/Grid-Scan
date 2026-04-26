"""Forecast error calculation and growth rate detection."""


def calculate_error(forecast_mw: float, actual_mw: float) -> dict:
    """
    Return error in MW and as percentage of forecast.

    Args:
        forecast_mw: Forecasted demand in MW.
        actual_mw: Actual demand in MW.

    Returns:
        Dict with error_mw and error_pct.
    """
    error_mw = actual_mw - forecast_mw
    error_pct = error_mw / forecast_mw if forecast_mw != 0 else 0.0
    return {
        "error_mw": round(error_mw, 1),
        "error_pct": round(error_pct, 6),
    }


def calculate_growth_rate(snapshots: list[dict]) -> float:
    """
    Compute error growth rate via linear regression over recent snapshots.

    Args:
        snapshots: List of dicts, each with 'error_mw' and 'captured_at'.
                   Must be sorted by time ascending.

    Returns:
        Growth rate in MW per hour. Positive means error is increasing.
    """
    if len(snapshots) < 2:
        return 0.0

    errors = [s["error_mw"] for s in snapshots]
    n = len(errors)

    # x-axis: index in 5-minute intervals, convert slope to per-hour
    x_mean = (n - 1) / 2.0
    y_mean = sum(errors) / n

    numerator = sum((i - x_mean) * (errors[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0

    # Slope is MW per 5-minute interval; multiply by 12 for MW/hour
    slope_per_interval = numerator / denominator
    growth_rate = slope_per_interval * 12.0
    return round(growth_rate, 1)


def is_dangerous(
    error_pct: float,
    growth_rate: float,
    error_threshold: float = 0.05,
    growth_threshold: float = 1000.0,
) -> bool:
    """
    Return True if either error percentage or growth rate breaches threshold.

    Args:
        error_pct: Absolute forecast error as fraction.
        growth_rate: Error growth rate in MW/hour.
        error_threshold: Fraction threshold for error_pct.
        growth_threshold: MW/hour threshold for growth rate.

    Returns:
        True if conditions are dangerous.
    """
    return abs(error_pct) >= error_threshold or abs(growth_rate) >= growth_threshold
