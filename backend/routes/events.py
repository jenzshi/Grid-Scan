"""GET /api/ercot/events — paginated event list and detail."""

from fastapi import APIRouter, Query

from backend.storage.supabase_client import get_events, get_event_by_id

router = APIRouter(prefix="/api/ercot", tags=["events"])


@router.get("/events")
def list_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return paginated event list, newest first."""
    events = get_events(limit=limit, offset=offset)
    return {"events": events, "limit": limit, "offset": offset}


@router.get("/events/{event_id}")
def get_event_detail(event_id: str):
    """Return full event detail including raw snapshot."""
    event = get_event_by_id(event_id)
    if event is None:
        return {"error": "Event not found"}, 404
    return event
