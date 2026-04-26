"""Response lag measurement — how quickly ERCOT responds to stress events."""

from datetime import datetime


_RESPONSE_TYPES = {"conservation_appeal", "eea1", "eea2", "eea3"}


def find_response_time(
    event_start: datetime,
    ops_messages: list[dict],
) -> int | None:
    """
    Scan ops messages for conservation appeal or EEA after event_start.

    Args:
        event_start: When the stress event was first detected.
        ops_messages: List of dicts with 'timestamp' and 'type' keys.

    Returns:
        Minutes to first response, or None if no response found.
    """
    earliest_response = None

    for msg in ops_messages:
        msg_type = msg.get("type", "")
        if msg_type not in _RESPONSE_TYPES:
            continue

        msg_time = _parse_timestamp(msg.get("timestamp"))
        if msg_time is None:
            continue

        if msg_time <= event_start:
            continue

        if earliest_response is None or msg_time < earliest_response:
            earliest_response = msg_time

    if earliest_response is None:
        return None

    delta = earliest_response - event_start
    lag_minutes = int(delta.total_seconds() / 60)
    return lag_minutes


def assess_adequacy(
    growth_rate_mw_per_hour: float,
    response_lag_minutes: int | None,
) -> bool:
    """
    Determine if ERCOT's response arrived before conditions became critical.

    Uses growth rate to estimate time to crisis, compares to lag.
    If growth rate is slow or response was fast, returns True.

    Args:
        growth_rate_mw_per_hour: How fast error is growing.
        response_lag_minutes: Minutes to first ERCOT action.

    Returns:
        True if response was adequate.
    """
    if response_lag_minutes is None:
        return False

    # Estimate minutes until 5000 MW additional error at current growth rate
    if growth_rate_mw_per_hour <= 0:
        return True

    minutes_to_crisis = (5000.0 / growth_rate_mw_per_hour) * 60
    return response_lag_minutes < minutes_to_crisis


def _parse_timestamp(timestamp) -> datetime | None:
    """
    Parse a timestamp string or datetime into a datetime object.

    Args:
        timestamp: ISO format string or datetime.

    Returns:
        Datetime object or None if unparseable.
    """
    if isinstance(timestamp, datetime):
        return timestamp
    if isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp)
        except ValueError:
            return None
    return None
