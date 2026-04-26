"""Training loop, validation, and checkpoint management for DemandLSTM."""

import logging
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from backend.ml.model import DemandLSTM

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
DEFAULT_CHECKPOINT_PATH = CACHE_DIR / "demand_model.pt"


def select_device() -> torch.device:
    """
    Select the best available device: MPS (Apple Silicon), CUDA, or CPU.

    Returns:
        torch.device for training.
    """
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def train_model(model: DemandLSTM, train_loader: DataLoader,
                val_loader: DataLoader, epochs: int = 30,
                learning_rate: float = 1e-3,
                stress_loss_weight: float = 0.1) -> dict:
    """
    Train the LSTM model with Huber loss for regression and BCE for stress.

    Args:
        model: DemandLSTM instance.
        train_loader: Training DataLoader.
        val_loader: Validation DataLoader.
        epochs: Number of training epochs.
        learning_rate: Adam learning rate.
        stress_loss_weight: Weight for stress classification loss.

    Returns:
        Dict with training history (train_loss, val_loss per epoch).
    """
    device = select_device()
    logger.info("Training on device: %s", device)
    model = model.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5,
    )
    regression_loss_fn = nn.HuberLoss()
    stress_loss_fn = nn.BCEWithLogitsLoss()

    history = {"train_loss": [], "val_loss": [], "val_mae": []}
    best_val_loss = float("inf")

    for epoch in range(epochs):
        start_time = time.time()

        train_loss = _train_epoch(
            model, train_loader, optimizer, regression_loss_fn,
            stress_loss_fn, stress_loss_weight, device,
        )
        val_loss, val_mae = _validate_epoch(
            model, val_loader, regression_loss_fn,
            stress_loss_fn, stress_loss_weight, device,
        )

        scheduler.step(val_loss)
        elapsed = time.time() - start_time

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_mae"].append(val_mae)

        logger.info(
            "Epoch %d/%d — train_loss: %.4f, val_loss: %.4f, val_mae: %.1f MW (%.1fs)",
            epoch + 1, epochs, train_loss, val_loss, val_mae, elapsed,
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            save_checkpoint(model, DEFAULT_CHECKPOINT_PATH)
            logger.info("Saved best checkpoint (val_loss=%.4f)", val_loss)

    return history


def _train_epoch(model: DemandLSTM, loader: DataLoader,
                 optimizer: torch.optim.Optimizer,
                 regression_loss_fn: nn.Module,
                 stress_loss_fn: nn.Module,
                 stress_weight: float,
                 device: torch.device) -> float:
    """
    Run one training epoch.

    Args:
        model: The LSTM model.
        loader: Training DataLoader.
        optimizer: Optimizer.
        regression_loss_fn: Loss for regression targets.
        stress_loss_fn: Loss for stress classification.
        stress_weight: Weight for stress loss in combined loss.
        device: Training device.

    Returns:
        Average training loss for the epoch.
    """
    model.train()
    total_loss = 0.0
    n_batches = 0

    for windows, targets, stress in loader:
        windows = windows.to(device)
        targets = targets.to(device)
        stress = stress.to(device).unsqueeze(1)

        optimizer.zero_grad()
        reg_pred, stress_pred = model(windows)

        reg_loss = regression_loss_fn(reg_pred, targets)
        stress_loss = stress_loss_fn(stress_pred, stress)
        loss = reg_loss + stress_weight * stress_loss

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


def _validate_epoch(model: DemandLSTM, loader: DataLoader,
                    regression_loss_fn: nn.Module,
                    stress_loss_fn: nn.Module,
                    stress_weight: float,
                    device: torch.device) -> tuple[float, float]:
    """
    Run one validation epoch.

    Args:
        model: The LSTM model.
        loader: Validation DataLoader.
        regression_loss_fn: Loss for regression targets.
        stress_loss_fn: Loss for stress classification.
        stress_weight: Weight for stress loss.
        device: Device.

    Returns:
        Tuple of (average val loss, average MAE in normalized units).
    """
    model.eval()
    total_loss = 0.0
    total_mae = 0.0
    n_batches = 0

    with torch.no_grad():
        for windows, targets, stress in loader:
            windows = windows.to(device)
            targets = targets.to(device)
            stress = stress.to(device).unsqueeze(1)

            reg_pred, stress_pred = model(windows)

            reg_loss = regression_loss_fn(reg_pred, targets)
            stress_loss = stress_loss_fn(stress_pred, stress)
            loss = reg_loss + stress_weight * stress_loss

            mae = torch.abs(reg_pred - targets).mean()

            total_loss += loss.item()
            total_mae += mae.item()
            n_batches += 1

    avg_loss = total_loss / max(n_batches, 1)
    avg_mae = total_mae / max(n_batches, 1)
    return avg_loss, avg_mae


def save_checkpoint(model: DemandLSTM, path: Path = DEFAULT_CHECKPOINT_PATH):
    """
    Save model checkpoint.

    Args:
        model: Trained model.
        path: File path for the .pt checkpoint.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "input_dim": model.input_dim,
        "hidden_dim": model.hidden_dim,
        "num_layers": model.num_layers,
    }
    torch.save(checkpoint, path)


def load_checkpoint(path: Path = DEFAULT_CHECKPOINT_PATH) -> DemandLSTM:
    """
    Load model from checkpoint.

    Args:
        path: File path for the .pt checkpoint.

    Returns:
        DemandLSTM with loaded weights.
    """
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    model = DemandLSTM(
        input_dim=checkpoint["input_dim"],
        hidden_dim=checkpoint["hidden_dim"],
        num_layers=checkpoint["num_layers"],
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model
