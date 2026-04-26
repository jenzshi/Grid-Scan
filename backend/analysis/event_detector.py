"""Detect and resolve stress events from snapshot data."""

import uuid
import logging
from datetime import datetime, timezone

from backend.config import GRIDS

logger = logging.getLogger(__name__)

_ERCOT = GRIDS["ERCOT"]
_ERROR_FLAG_PCT = _ERCOT["error_flag_pct"]
_GROWTH_DANGER = _ERCOT["growth_rate_danger_mw_per_hour"]

# Resolution: error must drop below half the flag threshold for 2+ cycles
_RESOLVE_PCT = _ERROR_FLAG_PCT * 0.5

# Module-level state tracking for active event
_active_event_id: str | None = None
_active_event_peak_error_mw: float = 0.0
_active_event_peak_error_pct: float = 0.0
_resolve_count: int = 0
_RESOLVE_CYCLES_NEEDED = 2


def detect_event(
    snapshot: dict,
    growth_rate: float,
) -> dict | None:
    """
    Check if a new stress event should be created.

    Returns a new event dict if conditions breach thresholds and
    no event is currently active. Returns None otherwise.

    Args:
        snapshot: Current snapshot dict with error_mw, error_pct, etc.
        growth_rate: Current error growth rate in MW/hour.

    Returns:
        Event dict ready for storage, or None.
    """
    global _active_event_id, _active_event_peak_error_mw
    global _active_event_peak_error_pct

    error_pct = abs(snapshot.get("error_pct", 0.0))
    error_mw = abs(snapshot.get("error_mw", 0.0))
    is_dangerous = error_pct >= _ERROR_FLAG_PCT or abs(growth_rate) >= _GROWTH_DANGER

    if _active_event_id is not None:
        _update_peak(error_mw, error_pct)
        return None

    if not is_dangerous:
        return None

    event_id = str(uuid.uuid4())
    _active_event_id = event_id
    _active_event_peak_error_mw = error_mw
    _active_event_peak_error_pct = error_pct

    event = {
        "id": event_id,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "cause": snapshot.get("cause", "undetermined"),
        "peak_error_mw": error_mw,
        "peak_error_pct": error_pct,
        "error_growth_rate_mw_per_hour": growth_rate,
        "response_lag_minutes": None,
        "response_adequate": None,
        "fingerprint_match": None,
        "fingerprint_similarity": None,
        "plain_summary": None,
        "raw_snapshot": snapshot,
    }

    logger.info("Stress event detected: %s (%.1f MW, %.1f%%)",
                event_id, error_mw, error_pct * 100)
    return event


def check_event_resolution(
    snapshot: dict,
    growth_rate: float,
) -> bool:
    """
    Check if the active event has resolved.

    Resolution requires error to drop below threshold for
    multiple consecutive cycles to avoid flapping.

    Args:
        snapshot: Current snapshot dict.
        growth_rate: Current error growth rate in MW/hour.

    Returns:
        True if the event just resolved, False otherwise.
    """
    global _active_event_id, _resolve_count
    global _active_event_peak_error_mw, _active_event_peak_error_pct

    if _active_event_id is None:
        return False

    error_pct = abs(snapshot.get("error_pct", 0.0))
    is_calm = error_pct < _RESOLVE_PCT and abs(growth_rate) < _GROWTH_DANGER * 0.5

    if is_calm:
        _resolve_count += 1
    else:
        _resolve_count = 0
        _update_peak(abs(snapshot.get("error_mw", 0.0)), error_pct)

    if _resolve_count >= _RESOLVE_CYCLES_NEEDED:
        logger.info("Stress event resolved: %s", _active_event_id)
        _active_event_id = None
        _active_event_peak_error_mw = 0.0
        _active_event_peak_error_pct = 0.0
        _resolve_count = 0
        return True

    return False


def get_active_event_id() -> str | None:
    """
    Return the ID of the currently active stress event.

    Returns:
        Event UUID string or None.
    """
    return _active_event_id


def get_active_event_peaks() -> dict:
    """
    Return peak error values for the active event.

    Returns:
        Dict with peak_error_mw and peak_error_pct.
    """
    return {
        "peak_error_mw": _active_event_peak_error_mw,
        "peak_error_pct": _active_event_peak_error_pct,
    }


def _update_peak(error_mw: float, error_pct: float) -> None:
    """
    Update peak tracking if current values exceed stored peaks.

    Args:
        error_mw: Current absolute error in MW.
        error_pct: Current absolute error as fraction.
    """
    global _active_event_peak_error_mw, _active_event_peak_error_pct

    if error_mw > _active_event_peak_error_mw:
        _active_event_peak_error_mw = error_mw
    if error_pct > _active_event_peak_error_pct:
        _active_event_peak_error_pct = error_pct
