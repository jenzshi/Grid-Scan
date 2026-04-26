"""Load trained model and serve demand predictions."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from backend.ml.model import DemandLSTM
from backend.ml.dataset import NormalizationStats, WINDOW_SIZE, CACHE_DIR
from backend.ml.trainer import load_checkpoint, DEFAULT_CHECKPOINT_PATH

logger = logging.getLogger(__name__)

# Module-level cache for loaded model and stats
_model: DemandLSTM | None = None
_norm_stats: NormalizationStats | None = None
_feature_columns: list[str] | None = None


def is_model_available() -> bool:
    """Check whether a trained model checkpoint exists."""
    return DEFAULT_CHECKPOINT_PATH.exists()


def get_model_status() -> dict:
    """
    Return metadata about the current model.

    Returns:
        Dict with available, checkpoint_path, parameters, input_dim,
        hidden_dim, num_layers, window_size.
    """
    if not is_model_available():
        return {"available": False, "message": "No trained model found"}

    model = _ensure_model_loaded()
    return {
        "available": True,
        "checkpoint_path": str(DEFAULT_CHECKPOINT_PATH),
        "parameters": model.count_parameters(),
        "input_dim": model.input_dim,
        "hidden_dim": model.hidden_dim,
        "num_layers": model.num_layers,
        "window_size": WINDOW_SIZE,
        "architecture": "LSTM",
    }


def predict(recent_features: np.ndarray) -> dict:
    """
    Generate demand predictions from a window of recent features.

    Args:
        recent_features: Array of shape (window_size, n_features) with
            the most recent hourly feature vectors in chronological order.

    Returns:
        Dict with demand_1h_mw, demand_4h_mw, demand_12h_mw,
        stress_probability, generated_at.
    """
    model = _ensure_model_loaded()
    norm_stats = _ensure_norm_stats_loaded()

    # Normalize
    normalized = norm_stats.normalize_features(recent_features)
    input_tensor = torch.FloatTensor(normalized).unsqueeze(0)

    # Predict
    model.eval()
    with torch.no_grad():
        reg_pred, stress_pred = model(input_tensor)

    # Denormalize regression predictions
    reg_values = reg_pred.numpy()[0]
    demand_mw = norm_stats.denormalize_targets(reg_values)

    # Stress probability via sigmoid
    stress_prob = torch.sigmoid(stress_pred).item()

    return {
        "demand_1h_mw": round(float(demand_mw[0]), 1),
        "demand_4h_mw": round(float(demand_mw[1]), 1),
        "demand_12h_mw": round(float(demand_mw[2]), 1),
        "stress_probability": round(stress_prob, 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def predict_from_dataframe(feature_df) -> dict:
    """
    Generate predictions from a pandas DataFrame with feature columns.

    Takes the last WINDOW_SIZE rows and extracts the correct feature columns.

    Args:
        feature_df: DataFrame with the same columns used during training.

    Returns:
        Prediction dict (same as predict()).
    """
    columns = _ensure_feature_columns_loaded()

    # Ensure we have enough rows
    if len(feature_df) < WINDOW_SIZE:
        return {
            "error": f"Need {WINDOW_SIZE} rows, got {len(feature_df)}",
            "available": False,
        }

    # Extract the last window
    window_df = feature_df[columns].tail(WINDOW_SIZE)
    features = window_df.values.astype(np.float32)

    return predict(features)


def _ensure_model_loaded() -> DemandLSTM:
    """Load model from checkpoint if not already cached."""
    global _model
    if _model is None:
        _model = load_checkpoint(DEFAULT_CHECKPOINT_PATH)
        logger.info("Loaded demand model (%d params)", _model.count_parameters())
    return _model


def _ensure_norm_stats_loaded() -> NormalizationStats:
    """Load normalization stats if not already cached."""
    global _norm_stats
    if _norm_stats is None:
        stats_path = CACHE_DIR / "norm_stats.json"
        _norm_stats = NormalizationStats.load(stats_path)
        logger.info("Loaded normalization stats")
    return _norm_stats


def _ensure_feature_columns_loaded() -> list[str]:
    """Load feature column order if not already cached."""
    global _feature_columns
    if _feature_columns is None:
        path = CACHE_DIR / "feature_columns.json"
        with open(path) as f:
            _feature_columns = json.load(f)
        logger.info("Loaded %d feature columns", len(_feature_columns))
    return _feature_columns


def reload_model():
    """Force reload of model and stats from disk."""
    global _model, _norm_stats, _feature_columns
    _model = None
    _norm_stats = None
    _feature_columns = None
    logger.info("Model cache cleared — will reload on next prediction")
