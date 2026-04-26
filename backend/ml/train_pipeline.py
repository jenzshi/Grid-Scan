"""End-to-end training pipeline: download -> features -> train -> save.

Run with: python -m backend.ml.train_pipeline
"""

import logging
import sys
import time

import numpy as np

from backend.ml.data_downloader import (
    download_ercot_load,
    download_weather,
    is_data_cached,
    load_cached_data,
)
from backend.ml.historical_features import (
    build_feature_matrix,
    get_feature_columns,
    get_target_columns,
)
from backend.ml.dataset import (
    create_dataloaders,
    CACHE_DIR,
)
from backend.ml.model import DemandLSTM
from backend.ml.trainer import train_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_EPOCHS = 30
DEFAULT_LR = 1e-3


def run_pipeline(start_year: int = 2021, end_year: int = 2025,
                 epochs: int = DEFAULT_EPOCHS,
                 learning_rate: float = DEFAULT_LR):
    """
    Execute the full training pipeline.

    Steps:
    1. Download (or load cached) ERCOT load and weather data.
    2. Build feature matrix.
    3. Create DataLoaders with normalization.
    4. Initialize and train DemandLSTM.
    5. Save checkpoint and normalization stats.

    Args:
        start_year: First year of data.
        end_year: Last year of data.
        epochs: Training epochs.
        learning_rate: Adam learning rate.
    """
    pipeline_start = time.time()

    # Step 1: Data
    logger.info("=== Step 1: Data Download ===")
    if is_data_cached(start_year, end_year):
        logger.info("Loading from cache...")
        load_df, weather_df = load_cached_data(start_year, end_year)
    else:
        logger.info("Downloading ERCOT load data...")
        load_df = download_ercot_load(start_year, end_year)
        logger.info("Downloading weather data...")
        weather_df = download_weather(start_year, end_year)

    logger.info("Load data: %d rows, Weather data: %d rows",
                len(load_df), len(weather_df))

    # Step 2: Features
    logger.info("=== Step 2: Feature Engineering ===")
    feature_df = build_feature_matrix(load_df, weather_df)

    feature_cols = get_feature_columns(feature_df)
    target_cols = get_target_columns()

    features = feature_df[feature_cols].values.astype(np.float32)
    targets = feature_df[target_cols].values.astype(np.float32)
    stress = feature_df["is_stress"].values.astype(np.float32)

    logger.info("Features: %d rows x %d columns", features.shape[0], features.shape[1])
    logger.info("Feature columns: %s", feature_cols)

    # Step 3: DataLoaders
    logger.info("=== Step 3: Creating DataLoaders ===")
    train_loader, val_loader, norm_stats = create_dataloaders(
        features, targets, stress,
    )
    norm_stats.save(CACHE_DIR / "norm_stats.json")
    logger.info("Normalization stats saved")

    # Step 4: Model
    logger.info("=== Step 4: Model Initialization ===")
    input_dim = features.shape[1]
    model = DemandLSTM(input_dim=input_dim)
    logger.info("DemandLSTM: %d parameters, input_dim=%d",
                model.count_parameters(), input_dim)

    # Step 5: Training
    logger.info("=== Step 5: Training ===")
    history = train_model(
        model, train_loader, val_loader,
        epochs=epochs, learning_rate=learning_rate,
    )

    # Step 6: Summary
    elapsed = time.time() - pipeline_start
    best_val_loss = min(history["val_loss"])
    best_epoch = history["val_loss"].index(best_val_loss) + 1

    # Save feature column list for inference
    _save_feature_columns(feature_cols)

    logger.info("=== Pipeline Complete ===")
    logger.info("Total time: %.1f seconds", elapsed)
    logger.info("Best val loss: %.4f (epoch %d)", best_val_loss, best_epoch)
    logger.info("Final val MAE (normalized): %.4f", history["val_mae"][-1])
    logger.info("Checkpoint: %s", CACHE_DIR / "demand_model.pt")

    return history


def _save_feature_columns(columns: list[str]):
    """
    Save feature column order for inference consistency.

    Args:
        columns: Ordered list of feature column names.
    """
    import json
    path = CACHE_DIR / "feature_columns.json"
    with open(path, "w") as f:
        json.dump(columns, f)
    logger.info("Feature columns saved to %s", path)


if __name__ == "__main__":
    # Allow overriding epochs from command line
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EPOCHS
    run_pipeline(epochs=epochs)
