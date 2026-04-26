"""Feature engineering pipeline for ML training data export."""

import math
import logging
from datetime import datetime, timezone

from backend.storage.supabase_client import get_recent_snapshots, get_events

logger = logging.getLogger(__name__)

# Snapshot fields that become raw features
_RAW_FIELDS = [
    "forecast_mw", "actual_mw", "error_mw", "error_pct",
    "reserve_margin_mw", "physical_responsive_capability_mw",
    "thermal_outage_mw", "reserve_price_adder", "weather_temp_f",
    "stress_score", "wind_actual_mw", "wind_forecast_mw",
    "wind_shortfall_mw", "solar_actual_mw", "solar_forecast_mw",
    "solar_shortfall_mw", "gas_generation_mw", "nuclear_generation_mw",
    "coal_generation_mw", "storage_mw",
]

# Rolling window sizes in number of snapshots (5-min intervals)
_ROLLING_WINDOWS = {
    "1h": 12,
    "4h": 48,
    "24h": 288,
}


def export_training_data(snapshots: list[dict], events: list[dict]) -> list[dict]:
    """
    Transform raw snapshots into feature-enriched training rows.

    Each row includes raw fields, derived features (rolling stats,
    rates of change, cyclical time encoding), and labels from events.

    Args:
        snapshots: List of snapshot dicts sorted by time ascending.
        events: List of event dicts for label computation.

    Returns:
        List of feature dicts, one per snapshot.
    """
    if not snapshots:
        return []

    labeled = _attach_labels(snapshots, events)
    enriched = _add_derived_features(labeled)
    return enriched


def get_collection_stats() -> dict:
    """
    Return statistics about collected training data.

    Returns:
        Dict with snapshot_count, hours_collected, estimated_rows,
        fields_per_row, collection_start, and readiness assessment.
    """
    snapshots = get_recent_snapshots(hours=24 * 365)
    count = len(snapshots)

    hours = count * 5 / 60.0
    days = hours / 24.0

    first_ts = snapshots[0].get("captured_at", "") if snapshots else None
    fields = len(_RAW_FIELDS) + _count_derived_fields()

    readiness = _assess_readiness(count)

    return {
        "snapshot_count": count,
        "hours_collected": round(hours, 1),
        "days_collected": round(days, 1),
        "fields_per_row": fields,
        "collection_start": first_ts,
        "readiness": readiness,
    }


def _attach_labels(snapshots: list[dict], events: list[dict]) -> list[dict]:
    """
    Label each snapshot with event context.

    Adds: stress_event_active (bool), time_to_event_minutes (float or None),
    event_severity (str or None).

    Args:
        snapshots: Sorted snapshot list.
        events: Event list with detected_at and resolved_at.

    Returns:
        Snapshots with label fields added.
    """
    event_ranges = _parse_event_ranges(events)

    for snap in snapshots:
        snap_time = _parse_timestamp(snap.get("captured_at", ""))
        if snap_time is None:
            snap["stress_event_active"] = False
            snap["time_to_event_minutes"] = None
            snap["event_severity"] = None
            continue

        active, severity = _check_in_event(snap_time, event_ranges)
        snap["stress_event_active"] = active
        snap["event_severity"] = severity

        time_to = _time_to_next_event(snap_time, event_ranges)
        snap["time_to_event_minutes"] = time_to

    return snapshots


def _add_derived_features(snapshots: list[dict]) -> list[dict]:
    """
    Compute derived features for each snapshot.

    Adds rolling means/std, rates of change, cyclical time encoding,
    and interaction features.

    Args:
        snapshots: Labeled snapshot list.

    Returns:
        Snapshots with derived feature fields added.
    """
    error_vals = [s.get("error_mw", 0.0) for s in snapshots]
    prc_vals = [s.get("physical_responsive_capability_mw", 0.0) for s in snapshots]
    score_vals = [s.get("stress_score", 0.0) for s in snapshots]
    wind_vals = [s.get("wind_shortfall_mw", 0.0) for s in snapshots]

    for i, snap in enumerate(snapshots):
        # Cyclical time features
        snap_time = _parse_timestamp(snap.get("captured_at", ""))
        if snap_time:
            hour = snap_time.hour + snap_time.minute / 60.0
            snap["hour_sin"] = round(math.sin(2 * math.pi * hour / 24.0), 6)
            snap["hour_cos"] = round(math.cos(2 * math.pi * hour / 24.0), 6)
            day_of_week = snap_time.weekday()
            snap["dow_sin"] = round(math.sin(2 * math.pi * day_of_week / 7.0), 6)
            snap["dow_cos"] = round(math.cos(2 * math.pi * day_of_week / 7.0), 6)
        else:
            snap["hour_sin"] = 0.0
            snap["hour_cos"] = 1.0
            snap["dow_sin"] = 0.0
            snap["dow_cos"] = 1.0

        # Rolling statistics
        for window_name, window_size in _ROLLING_WINDOWS.items():
            start = max(0, i - window_size + 1)
            window = error_vals[start:i + 1]
            snap[f"error_mw_mean_{window_name}"] = _safe_mean(window)
            snap[f"error_mw_std_{window_name}"] = _safe_std(window)

            prc_window = prc_vals[start:i + 1]
            snap[f"prc_mean_{window_name}"] = _safe_mean(prc_window)

            score_window = score_vals[start:i + 1]
            snap[f"score_mean_{window_name}"] = _safe_mean(score_window)

        # Rate of change (vs 1h ago)
        lookback = min(i, 12)
        if lookback > 0:
            snap["error_roc_1h"] = round(error_vals[i] - error_vals[i - lookback], 1)
            snap["prc_roc_1h"] = round(prc_vals[i] - prc_vals[i - lookback], 1)
            snap["wind_shortfall_roc_1h"] = round(
                wind_vals[i] - wind_vals[i - lookback], 1
            )
        else:
            snap["error_roc_1h"] = 0.0
            snap["prc_roc_1h"] = 0.0
            snap["wind_shortfall_roc_1h"] = 0.0

        # Interaction features
        error_pct = abs(snap.get("error_pct", 0.0))
        thermal = snap.get("thermal_outage_mw", 0.0)
        snap["error_x_thermal"] = round(error_pct * thermal, 1)
        snap["error_x_wind_shortfall"] = round(
            error_pct * snap.get("wind_shortfall_mw", 0.0), 1
        )

    return snapshots


def _parse_event_ranges(events: list[dict]) -> list[dict]:
    """
    Parse event timestamps into start/end datetime pairs.

    Args:
        events: Raw event dicts.

    Returns:
        List of dicts with start, end (or None), severity.
    """
    ranges = []
    for ev in events:
        start = _parse_timestamp(ev.get("detected_at", ""))
        end = _parse_timestamp(ev.get("resolved_at") or "")
        if start is None:
            continue
        severity = _event_severity(ev)
        ranges.append({"start": start, "end": end, "severity": severity})
    return ranges


def _event_severity(event: dict) -> str:
    """
    Determine severity label from event metrics.

    Args:
        event: Event dict.

    Returns:
        'critical', 'high', 'moderate', or 'low'.
    """
    error_pct = abs(event.get("peak_error_pct", 0.0))
    growth = abs(event.get("error_growth_rate_mw_per_hour", 0.0))

    if error_pct >= 0.10 or growth >= 1500:
        return "critical"
    if error_pct >= 0.07 or growth >= 1000:
        return "high"
    if error_pct >= 0.05:
        return "moderate"
    return "low"


def _check_in_event(
    snap_time: datetime, event_ranges: list[dict]
) -> tuple[bool, str | None]:
    """
    Check if a timestamp falls within any event range.

    Args:
        snap_time: Snapshot datetime.
        event_ranges: Parsed event ranges.

    Returns:
        Tuple of (is_active, severity_or_none).
    """
    for er in event_ranges:
        if snap_time < er["start"]:
            continue
        if er["end"] is None or snap_time <= er["end"]:
            return True, er["severity"]
    return False, None


def _time_to_next_event(
    snap_time: datetime, event_ranges: list[dict]
) -> float | None:
    """
    Compute minutes until the next event starts.

    Args:
        snap_time: Snapshot datetime.
        event_ranges: Parsed event ranges.

    Returns:
        Minutes to next event, or None if no future event.
    """
    min_delta = None
    for er in event_ranges:
        if er["start"] > snap_time:
            delta = (er["start"] - snap_time).total_seconds() / 60.0
            if min_delta is None or delta < min_delta:
                min_delta = delta
    return round(min_delta, 1) if min_delta is not None else None


def _parse_timestamp(ts_str: str) -> datetime | None:
    """
    Parse an ISO timestamp string to a timezone-aware datetime.

    Args:
        ts_str: ISO format timestamp string.

    Returns:
        Datetime or None if parsing fails.
    """
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _safe_mean(values: list[float]) -> float:
    """Compute mean, returning 0.0 for empty lists."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def _safe_std(values: list[float]) -> float:
    """Compute standard deviation, returning 0.0 for short lists."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return round(math.sqrt(variance), 1)


def _count_derived_fields() -> int:
    """Count the number of derived feature fields added per row."""
    # cyclical: 4, rolling: 4 fields * 3 windows = 12, roc: 3, interaction: 2, labels: 3
    return 4 + 12 + 3 + 2 + 3


def _assess_readiness(snapshot_count: int) -> dict:
    """
    Assess ML training readiness based on data volume.

    Args:
        snapshot_count: Total snapshots collected.

    Returns:
        Dict with level, description, and milestones.
    """
    milestones = [
        (105120, "Full seasonal coverage (1 year)", "production_ready"),
        (51840, "Good training set (6 months)", "strong"),
        (25920, "Minimum for deep learning (3 months)", "viable"),
        (8640, "Enough for regression (1 month)", "preliminary"),
        (0, "Collecting data", "insufficient"),
    ]

    level = "insufficient"
    description = "Collecting data"
    for threshold, desc, lvl in milestones:
        if snapshot_count >= threshold:
            level = lvl
            description = desc
            break

    return {
        "level": level,
        "description": description,
        "snapshots_to_next": _snapshots_to_next(snapshot_count, milestones),
        "milestones": [
            {"count": t, "label": d, "reached": snapshot_count >= t}
            for t, d, _ in milestones
            if t > 0
        ],
    }


def _snapshots_to_next(count: int, milestones: list) -> int | None:
    """
    Compute snapshots needed to reach next milestone.

    Args:
        count: Current snapshot count.
        milestones: List of (threshold, description, level) tuples.

    Returns:
        Number of snapshots to next milestone, or None if all reached.
    """
    for threshold, _, _ in reversed(milestones):
        if threshold > count:
            return threshold - count
    return None
