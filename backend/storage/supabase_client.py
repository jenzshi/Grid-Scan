"""All database reads and writes. Uses in-memory store when MOCK_MODE is true."""

import uuid
import logging
from datetime import datetime, timezone

import httpx

from backend.config import MOCK_MODE, SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY
from backend.exceptions import SupabaseWriteError, SupabaseReadError

logger = logging.getLogger(__name__)

# In-memory backing store for mock mode
_snapshots: list[dict] = []
_events: list[dict] = []
_historical_periods: list[dict] = []


def _service_key() -> str:
    """Return the service role key, falling back to anon key."""
    return SUPABASE_SERVICE_KEY or SUPABASE_KEY


def _read_headers() -> dict:
    """Build Supabase REST API headers for reads (service role key, bypasses RLS)."""
    key = _service_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _write_headers() -> dict:
    """Build Supabase REST API headers for writes (service role key, bypasses RLS)."""
    key = _service_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _rest_url(table: str) -> str:
    """Build Supabase REST URL for a table."""
    return f"{SUPABASE_URL}/rest/v1/{table}"


def _reset_store():
    """Reset in-memory store. Used by tests."""
    global _snapshots, _events, _historical_periods
    _snapshots = []
    _events = []
    _historical_periods = []


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def save_snapshot(snapshot: dict) -> None:
    """Save a 5-minute grid data snapshot."""
    if MOCK_MODE:
        return _mock_save_snapshot(snapshot)
    try:
        record = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **snapshot,
        }
        resp = httpx.post(
            _rest_url("grid_snapshots"),
            json=record,
            headers=_write_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise SupabaseWriteError(f"Failed to save snapshot: {exc}") from exc


def get_recent_snapshots(hours: int = 24) -> list[dict]:
    """Return snapshots from the last N hours."""
    if MOCK_MODE:
        return _mock_get_recent_snapshots(hours)
    try:
        cutoff = datetime.now(timezone.utc)
        cutoff_iso = (
            cutoff.replace(microsecond=0)
            .__sub__(__import__("datetime").timedelta(hours=hours))
            .isoformat()
        )
        resp = httpx.get(
            _rest_url("grid_snapshots"),
            params={
                "captured_at": f"gte.{cutoff_iso}",
                "order": "captured_at.asc",
                "limit": "500",
            },
            headers=_read_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise SupabaseReadError(f"Failed to read snapshots: {exc}") from exc


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def save_event(event: dict) -> None:
    """Save a stress event record."""
    if MOCK_MODE:
        return _mock_save_event(event)
    try:
        record = {
            "id": event.get("id", str(uuid.uuid4())),
            **event,
        }
        resp = httpx.post(
            _rest_url("stress_events"),
            json=record,
            headers=_write_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise SupabaseWriteError(f"Failed to save event: {exc}") from exc


def update_event(event_id: str, updates: dict) -> None:
    """Update fields on an existing event."""
    if MOCK_MODE:
        return _mock_update_event(event_id, updates)
    try:
        resp = httpx.patch(
            _rest_url("stress_events"),
            params={"id": f"eq.{event_id}"},
            json=updates,
            headers=_write_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise SupabaseWriteError(f"Failed to update event: {exc}") from exc


def get_events(limit: int = 50, offset: int = 0) -> list[dict]:
    """Return paginated event list, newest first."""
    if MOCK_MODE:
        return _mock_get_events(limit, offset)
    try:
        resp = httpx.get(
            _rest_url("stress_events"),
            params={
                "order": "detected_at.desc",
                "limit": str(limit),
                "offset": str(offset),
            },
            headers=_read_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise SupabaseReadError(f"Failed to read events: {exc}") from exc


def get_event_by_id(event_id: str) -> dict | None:
    """Return a single event by ID, or None."""
    if MOCK_MODE:
        return _mock_get_event_by_id(event_id)
    try:
        resp = httpx.get(
            _rest_url("stress_events"),
            params={"id": f"eq.{event_id}", "limit": "1"},
            headers=_read_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None
    except Exception as exc:
        raise SupabaseReadError(f"Failed to read event: {exc}") from exc


def get_trend_aggregates() -> dict:
    """Return pre-aggregated trend statistics."""
    if MOCK_MODE:
        return _mock_get_trend_aggregates()
    try:
        events = get_events(limit=200)
        return _aggregate_trends(events)
    except Exception as exc:
        raise SupabaseReadError(f"Failed to aggregate trends: {exc}") from exc


# ---------------------------------------------------------------------------
# Historical periods
# ---------------------------------------------------------------------------

def save_historical_period(period: dict) -> None:
    """Save a historical peak period record."""
    if MOCK_MODE:
        return _mock_save_historical_period(period)
    try:
        record = {
            "id": period.get("id", str(uuid.uuid4())),
            **period,
        }
        resp = httpx.post(
            _rest_url("historical_periods"),
            json=record,
            headers=_write_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise SupabaseWriteError(
            f"Failed to save historical period: {exc}"
        ) from exc


def get_historical_periods(season: str | None = None) -> list[dict]:
    """Return all historical periods, optionally filtered by season."""
    if MOCK_MODE:
        return _mock_get_historical_periods(season)
    try:
        params = {"order": "year.asc", "limit": "500"}
        if season:
            params["season"] = f"eq.{season}"
        resp = httpx.get(
            _rest_url("historical_periods"),
            params=params,
            headers=_read_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise SupabaseReadError(
            f"Failed to read historical periods: {exc}"
        ) from exc


def historical_archive_exists() -> bool:
    """Return True if historical_periods table has any rows."""
    if MOCK_MODE:
        return len(_historical_periods) > 0
    try:
        resp = httpx.get(
            _rest_url("historical_periods"),
            params={"limit": "1"},
            headers=_read_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return len(resp.json()) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Shared aggregation logic
# ---------------------------------------------------------------------------

def _aggregate_trends(events: list[dict]) -> dict:
    """Compute trend aggregates from a list of events."""
    monthly_events: dict[str, int] = {}
    monthly_lag: dict[str, list[float]] = {}
    cause_counts = {"demand_side": 0, "supply_side": 0}

    for event in events:
        detected = event.get("detected_at", "")
        if isinstance(detected, str) and len(detected) >= 7:
            month_key = detected[:7]
        else:
            continue

        monthly_events[month_key] = monthly_events.get(month_key, 0) + 1

        lag = event.get("response_lag_minutes")
        if lag is not None:
            monthly_lag.setdefault(month_key, []).append(lag)

        cause = event.get("cause", "")
        if cause in cause_counts:
            cause_counts[cause] += 1

    avg_lag_by_month = {
        month: sum(lags) / len(lags)
        for month, lags in monthly_lag.items()
    }

    return {
        "monthly_events": monthly_events,
        "avg_response_lag_by_month": avg_lag_by_month,
        "cause_breakdown": cause_counts,
    }


# ---------------------------------------------------------------------------
# Mock implementations (in-memory)
# ---------------------------------------------------------------------------

def _mock_save_snapshot(snapshot: dict) -> None:
    record = {
        "id": str(uuid.uuid4()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **snapshot,
    }
    _snapshots.append(record)


def _mock_get_recent_snapshots(hours: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    results = []
    for snap in _snapshots:
        captured = snap.get("captured_at", "")
        if isinstance(captured, str):
            try:
                ts = datetime.fromisoformat(captured).timestamp()
            except ValueError:
                continue
        else:
            ts = captured.timestamp()
        if ts >= cutoff:
            results.append(snap)
    return results


def _mock_save_event(event: dict) -> None:
    record = {
        "id": event.get("id", str(uuid.uuid4())),
        **event,
    }
    _events.append(record)


def _mock_update_event(event_id: str, updates: dict) -> None:
    for event in _events:
        if event["id"] == event_id:
            event.update(updates)
            return


def _mock_get_events(limit: int, offset: int) -> list[dict]:
    sorted_events = sorted(
        _events,
        key=lambda e: e.get("detected_at", ""),
        reverse=True,
    )
    return sorted_events[offset:offset + limit]


def _mock_get_event_by_id(event_id: str) -> dict | None:
    for event in _events:
        if event["id"] == event_id:
            return event
    return None


def _mock_get_trend_aggregates() -> dict:
    return _aggregate_trends(_events)


def delete_historical_periods_by_year_season(year: int, season: str) -> None:
    """
    Delete historical period rows matching a specific year and season.

    Args:
        year: The year to match.
        season: The season to match.
    """
    if MOCK_MODE:
        return _mock_delete_historical_periods(year, season)
    try:
        resp = httpx.delete(
            _rest_url("historical_periods"),
            params={"year": f"eq.{year}", "season": f"eq.{season}"},
            headers=_write_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise SupabaseWriteError(
            f"Failed to delete historical periods for {year}/{season}: {exc}"
        ) from exc


def _mock_delete_historical_periods(year: int, season: str) -> None:
    """Remove matching periods from in-memory store."""
    global _historical_periods
    _historical_periods = [
        p for p in _historical_periods
        if not (p.get("year") == year and p.get("season") == season)
    ]


def _mock_save_historical_period(period: dict) -> None:
    record = {
        "id": period.get("id", str(uuid.uuid4())),
        **period,
    }
    _historical_periods.append(record)


def _mock_get_historical_periods(season: str | None) -> list[dict]:
    if season:
        return [p for p in _historical_periods if p.get("season") == season]
    return list(_historical_periods)
