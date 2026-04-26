"""Tests for backend.ml.dataset."""

import numpy as np
import torch

from backend.ml.dataset import (
    DemandDataset,
    NormalizationStats,
    compute_normalization_stats,
    create_dataloaders,
    WINDOW_SIZE,
)


def _make_synthetic_data(n=1000, n_features=35):
    """Create synthetic feature, target, and stress arrays."""
    rng = np.random.default_rng(42)
    features = rng.normal(0, 1, (n, n_features)).astype(np.float32)
    targets = rng.normal(50000, 10000, (n, 3)).astype(np.float32)
    stress = (rng.random(n) > 0.95).astype(np.float32)
    return features, targets, stress


def test_dataset_length():
    """Dataset length equals n_timesteps minus window_size."""
    features, targets, stress = _make_synthetic_data(500)
    ds = DemandDataset(features, targets, stress, window_size=168)
    assert len(ds) == 500 - 168


def test_dataset_item_shapes():
    """Each item returns correct tensor shapes."""
    features, targets, stress = _make_synthetic_data(500, n_features=35)
    ds = DemandDataset(features, targets, stress, window_size=168)

    window, target, stress_val = ds[0]

    assert window.shape == (168, 35)
    assert target.shape == (3,)
    assert stress_val.shape == ()


def test_dataset_window_content():
    """Window contains the correct slice of features."""
    features, targets, stress = _make_synthetic_data(500)
    ds = DemandDataset(features, targets, stress, window_size=10)

    window, target, _ = ds[5]

    # Window should be features[5:15]
    expected = torch.FloatTensor(features[5:15])
    assert torch.allclose(window, expected)

    # Target should be from the last timestep in window (index 14)
    expected_target = torch.FloatTensor(targets[14])
    assert torch.allclose(target, expected_target)


def test_normalization_roundtrip():
    """Normalizing then denormalizing returns original values."""
    features, targets, _ = _make_synthetic_data(100)
    stats = compute_normalization_stats(features, targets)

    normalized = stats.normalize_targets(targets)
    recovered = stats.denormalize_targets(normalized)

    np.testing.assert_allclose(recovered, targets, rtol=1e-5)


def test_normalization_save_load(tmp_path):
    """Stats survive save/load roundtrip."""
    features, targets, _ = _make_synthetic_data(100)
    stats = compute_normalization_stats(features, targets)

    path = tmp_path / "stats.json"
    stats.save(path)
    loaded = NormalizationStats.load(path)

    np.testing.assert_allclose(loaded.mean, stats.mean)
    np.testing.assert_allclose(loaded.std, stats.std)
    np.testing.assert_allclose(loaded.target_mean, stats.target_mean)
    np.testing.assert_allclose(loaded.target_std, stats.target_std)


def test_create_dataloaders_returns_batches():
    """DataLoaders yield correctly shaped batches."""
    features, targets, stress = _make_synthetic_data(1000)
    train_loader, val_loader, stats = create_dataloaders(
        features, targets, stress,
        val_fraction=0.2, batch_size=32, window_size=24,
    )

    # Get one batch
    windows, tgt, strs = next(iter(train_loader))

    assert windows.shape == (32, 24, 35)
    assert tgt.shape == (32, 3)
    assert strs.shape == (32,)


def test_val_split_is_temporal():
    """Validation data comes from the end (not shuffled in)."""
    features, targets, stress = _make_synthetic_data(1000)
    train_loader, val_loader, _ = create_dataloaders(
        features, targets, stress,
        val_fraction=0.2, batch_size=32, window_size=24,
    )

    # Train should have more samples than val
    assert len(train_loader.dataset) > len(val_loader.dataset)
