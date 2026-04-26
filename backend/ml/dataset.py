"""PyTorch Dataset for sliding-window demand prediction."""

import json
import logging
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
WINDOW_SIZE = 168  # 1 week of hourly data
BATCH_SIZE = 64
VAL_FRACTION = 0.15  # last 15% of data for validation


class DemandDataset(Dataset):
    """
    Sliding window dataset for demand prediction.

    Each sample is a (window_size x n_features) input and
    (3 regression targets + 1 stress label) output from the last timestep.
    """

    def __init__(self, features: np.ndarray, targets: np.ndarray,
                 stress: np.ndarray, window_size: int = WINDOW_SIZE):
        """
        Initialize the dataset.

        Args:
            features: Array of shape (n_timesteps, n_features).
            targets: Array of shape (n_timesteps, 3) — t+1h, t+4h, t+12h.
            stress: Array of shape (n_timesteps,) — binary stress label.
            window_size: Number of timesteps per input window.
        """
        self.features = torch.FloatTensor(features)
        self.targets = torch.FloatTensor(targets)
        self.stress = torch.FloatTensor(stress)
        self.window_size = window_size

    def __len__(self):
        """Return number of valid windows."""
        return len(self.features) - self.window_size

    def __getitem__(self, idx):
        """
        Return one (input_window, regression_targets, stress_label) tuple.

        Args:
            idx: Window start index.

        Returns:
            Tuple of (window_tensor, target_tensor, stress_scalar).
        """
        end = idx + self.window_size
        window = self.features[idx:end]
        target = self.targets[end - 1]
        stress = self.stress[end - 1]
        return window, target, stress


class NormalizationStats:
    """Stores and applies feature normalization (z-score)."""

    def __init__(self, mean: np.ndarray, std: np.ndarray,
                 target_mean: np.ndarray, target_std: np.ndarray):
        """
        Initialize with precomputed statistics.

        Args:
            mean: Feature means, shape (n_features,).
            std: Feature stds, shape (n_features,).
            target_mean: Target means, shape (3,).
            target_std: Target stds, shape (3,).
        """
        self.mean = mean
        self.std = std
        self.target_mean = target_mean
        self.target_std = target_std

    def normalize_features(self, features: np.ndarray) -> np.ndarray:
        """Apply z-score normalization to features."""
        safe_std = np.where(self.std == 0, 1.0, self.std)
        return (features - self.mean) / safe_std

    def normalize_targets(self, targets: np.ndarray) -> np.ndarray:
        """Apply z-score normalization to targets."""
        safe_std = np.where(self.target_std == 0, 1.0, self.target_std)
        return (targets - self.target_mean) / safe_std

    def denormalize_targets(self, targets: np.ndarray) -> np.ndarray:
        """Reverse z-score normalization on targets."""
        return targets * self.target_std + self.target_mean

    def save(self, path: Path):
        """
        Save normalization stats to JSON.

        Args:
            path: File path for the JSON file.
        """
        data = {
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "target_mean": self.target_mean.tolist(),
            "target_std": self.target_std.tolist(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: Path) -> "NormalizationStats":
        """
        Load normalization stats from JSON.

        Args:
            path: File path for the JSON file.

        Returns:
            NormalizationStats instance.
        """
        with open(path) as f:
            data = json.load(f)
        return cls(
            mean=np.array(data["mean"]),
            std=np.array(data["std"]),
            target_mean=np.array(data["target_mean"]),
            target_std=np.array(data["target_std"]),
        )


def compute_normalization_stats(features: np.ndarray,
                                targets: np.ndarray) -> NormalizationStats:
    """
    Compute z-score normalization statistics from training data.

    Args:
        features: Training features, shape (n_timesteps, n_features).
        targets: Training targets, shape (n_timesteps, 3).

    Returns:
        NormalizationStats with computed mean and std.
    """
    return NormalizationStats(
        mean=features.mean(axis=0),
        std=features.std(axis=0),
        target_mean=targets.mean(axis=0),
        target_std=targets.std(axis=0),
    )


def create_dataloaders(features: np.ndarray, targets: np.ndarray,
                       stress: np.ndarray,
                       val_fraction: float = VAL_FRACTION,
                       batch_size: int = BATCH_SIZE,
                       window_size: int = WINDOW_SIZE
                       ) -> tuple[DataLoader, DataLoader, NormalizationStats]:
    """
    Create train and validation DataLoaders with temporal split.

    Computes normalization from training portion only, applies to both.

    Args:
        features: Full feature array, shape (n_timesteps, n_features).
        targets: Full target array, shape (n_timesteps, 3).
        stress: Full stress labels, shape (n_timesteps,).
        val_fraction: Fraction of data for validation (from the end).
        batch_size: Batch size for DataLoaders.
        window_size: Sliding window length.

    Returns:
        Tuple of (train_loader, val_loader, normalization_stats).
    """
    split_idx = int(len(features) * (1 - val_fraction))

    train_features = features[:split_idx]
    train_targets = targets[:split_idx]
    train_stress = stress[:split_idx]

    val_features = features[split_idx:]
    val_targets = targets[split_idx:]
    val_stress = stress[split_idx:]

    # Compute stats from training data only
    stats = compute_normalization_stats(train_features, train_targets)

    # Normalize
    train_features_norm = stats.normalize_features(train_features)
    val_features_norm = stats.normalize_features(val_features)
    train_targets_norm = stats.normalize_targets(train_targets)
    val_targets_norm = stats.normalize_targets(val_targets)

    train_ds = DemandDataset(train_features_norm, train_targets_norm,
                             train_stress, window_size)
    val_ds = DemandDataset(val_features_norm, val_targets_norm,
                           val_stress, window_size)

    train_loader = DataLoader(train_ds, batch_size=batch_size,
                              shuffle=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size,
                            shuffle=False, drop_last=False)

    logger.info("Train: %d samples, Val: %d samples",
                len(train_ds), len(val_ds))

    return train_loader, val_loader, stats
