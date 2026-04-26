"""GET /api/export/ — training data export and collection stats."""

import csv
import io
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.storage.supabase_client import get_recent_snapshots, get_events
from backend.ml.feature_pipeline import export_training_data, get_collection_stats

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/training-data")
def get_training_data(hours: int = 24):
    """
    Export feature-enriched training data as CSV.

    Args:
        hours: How many hours of snapshots to export.

    Returns:
        CSV file download.
    """
    snapshots = get_recent_snapshots(hours=hours)
    events = get_events(limit=500)
    rows = export_training_data(snapshots, events)

    if not rows:
        return StreamingResponse(
            io.StringIO("no data\n"),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=training_data.csv"},
        )

    output = io.StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=training_data.csv",
        },
    )


@router.get("/stats")
def get_stats():
    """
    Return data collection statistics and ML readiness assessment.

    Returns:
        Dict with collection stats and readiness milestones.
    """
    return get_collection_stats()
