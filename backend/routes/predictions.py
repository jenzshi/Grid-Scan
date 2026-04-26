"""Prediction API routes — demand forecasts and model status."""

import logging

from fastapi import APIRouter, HTTPException

from backend.ml.inference import (
    is_model_available,
    get_model_status,
    predict_from_dataframe,
    reload_model,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ercot", tags=["predictions"])


@router.get("/predictions")
def get_predictions():
    """
    Return demand predictions for t+1h, t+4h, t+12h and stress probability.

    Requires a trained model checkpoint and sufficient recent snapshot data.
    """
    if not is_model_available():
        raise HTTPException(
            status_code=503,
            detail="No trained model available. Run: python -m backend.ml.train_pipeline",
        )

    try:
        feature_df = _build_inference_features()
    except Exception as exc:
        logger.exception("Failed to build inference features")
        raise HTTPException(
            status_code=503,
            detail=f"Insufficient data for prediction: {exc}",
        ) from exc

    try:
        result = predict_from_dataframe(feature_df)
    except Exception as exc:
        logger.exception("Prediction failed")
        raise HTTPException(
            status_code=500,
            detail=f"Prediction error: {exc}",
        ) from exc

    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])

    return result


@router.get("/model/status")
def get_model_info():
    """Return metadata about the trained model."""
    return get_model_status()


@router.post("/model/reload")
def post_model_reload():
    """Force reload of model checkpoint from disk."""
    reload_model()
    return {"status": "ok", "message": "Model cache cleared"}


def _build_inference_features():
    """
    Build a feature DataFrame from recent snapshots for inference.

    Uses the same feature engineering as training but on recent data.
    Falls back to the last WINDOW_SIZE hours of cached historical data
    if real-time snapshots are insufficient.

    Returns:
        pandas DataFrame with feature columns.
    """
    import pandas as pd
    from backend.ml.dataset import WINDOW_SIZE
    from backend.ml.data_downloader import CACHE_DIR

    # Try loading the most recent cached data for inference
    # In production, this would use live snapshots from Supabase
    parquet_files = sorted(CACHE_DIR.glob("ercot_load_*.parquet"))
    if not parquet_files:
        raise FileNotFoundError("No cached ERCOT data for inference")

    # Use the most recent year's data
    load_df = pd.read_parquet(parquet_files[-1])

    weather_path = sorted(CACHE_DIR.glob("weather_*.parquet"))
    if not weather_path:
        raise FileNotFoundError("No cached weather data for inference")

    weather_df = pd.read_parquet(weather_path[-1])

    from backend.ml.historical_features import build_feature_matrix
    feature_df = build_feature_matrix(load_df, weather_df)

    if len(feature_df) < WINDOW_SIZE:
        raise ValueError(
            f"Need {WINDOW_SIZE} feature rows, only have {len(feature_df)}"
        )

    return feature_df
