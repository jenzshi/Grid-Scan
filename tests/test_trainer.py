"""Tests for backend.ml.trainer."""

import numpy as np
import torch
from torch.utils.data import DataLoader

from backend.ml.model import DemandLSTM
from backend.ml.dataset import DemandDataset
from backend.ml.trainer import (
    _train_epoch,
    _validate_epoch,
    save_checkpoint,
    load_checkpoint,
    select_device,
)


def _make_tiny_loader(n=256, n_features=10, window_size=24, batch_size=32):
    """Create a small DataLoader with synthetic data for fast testing."""
    rng = np.random.default_rng(42)
    features = rng.normal(0, 1, (n, n_features)).astype(np.float32)
    targets = rng.normal(0, 1, (n, 3)).astype(np.float32)
    stress = (rng.random(n) > 0.9).astype(np.float32)

    ds = DemandDataset(features, targets, stress, window_size=window_size)
    return DataLoader(ds, batch_size=batch_size, shuffle=True, drop_last=True)


def test_loss_decreases_on_synthetic_data():
    """Training loss decreases over a few epochs on tiny synthetic data."""
    model = DemandLSTM(input_dim=10, hidden_dim=32, num_layers=1)
    loader = _make_tiny_loader()
    device = torch.device("cpu")
    model = model.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    reg_loss_fn = torch.nn.HuberLoss()
    stress_loss_fn = torch.nn.BCEWithLogitsLoss()

    losses = []
    for _ in range(5):
        loss = _train_epoch(
            model, loader, optimizer,
            reg_loss_fn, stress_loss_fn, 0.1, device,
        )
        losses.append(loss)

    # Loss at epoch 5 should be lower than epoch 1
    assert losses[-1] < losses[0]


def test_validation_returns_loss_and_mae():
    """Validation epoch returns a loss and MAE value."""
    model = DemandLSTM(input_dim=10, hidden_dim=32, num_layers=1)
    loader = _make_tiny_loader()
    device = torch.device("cpu")
    model = model.to(device)

    reg_loss_fn = torch.nn.HuberLoss()
    stress_loss_fn = torch.nn.BCEWithLogitsLoss()

    val_loss, val_mae = _validate_epoch(
        model, loader, reg_loss_fn, stress_loss_fn, 0.1, device,
    )

    assert val_loss > 0
    assert val_mae >= 0


def test_checkpoint_roundtrip(tmp_path):
    """Model survives save/load checkpoint roundtrip."""
    model = DemandLSTM(input_dim=15, hidden_dim=64, num_layers=2)
    path = tmp_path / "test_model.pt"

    save_checkpoint(model, path)
    loaded = load_checkpoint(path)

    assert loaded.input_dim == 15
    assert loaded.hidden_dim == 64
    assert loaded.num_layers == 2
    assert loaded.count_parameters() == model.count_parameters()

    # Weights should match
    test_input = torch.randn(1, 24, 15)
    model.eval()
    loaded.eval()
    with torch.no_grad():
        orig_out = model(test_input)
        loaded_out = loaded(test_input)
    torch.testing.assert_close(orig_out[0], loaded_out[0])


def test_select_device_returns_valid():
    """select_device returns a valid torch.device."""
    device = select_device()
    assert isinstance(device, torch.device)
    assert device.type in ("cpu", "mps", "cuda")
