"""Tests for backend.ml.model."""

import torch

from backend.ml.model import DemandLSTM


def test_forward_pass_output_shapes():
    """Forward pass returns correct shapes for regression and stress heads."""
    model = DemandLSTM(input_dim=35, hidden_dim=64, num_layers=2)
    batch = torch.randn(8, 168, 35)

    regression, stress = model(batch)

    assert regression.shape == (8, 3)
    assert stress.shape == (8, 1)


def test_forward_pass_single_sample():
    """Model handles batch size of 1."""
    model = DemandLSTM(input_dim=20)
    batch = torch.randn(1, 168, 20)

    regression, stress = model(batch)

    assert regression.shape == (1, 3)
    assert stress.shape == (1, 1)


def test_parameter_count_reasonable():
    """Model has approximately 150K parameters (not millions)."""
    model = DemandLSTM(input_dim=35, hidden_dim=128, num_layers=2)
    count = model.count_parameters()

    assert 50_000 < count < 500_000


def test_different_input_dims():
    """Model initializes with different input dimensions."""
    for dim in [10, 35, 50]:
        model = DemandLSTM(input_dim=dim)
        batch = torch.randn(4, 168, dim)
        regression, stress = model(batch)
        assert regression.shape == (4, 3)


def test_different_sequence_lengths():
    """Model handles different sequence lengths (not just 168)."""
    model = DemandLSTM(input_dim=35)

    for seq_len in [24, 168, 336]:
        batch = torch.randn(4, seq_len, 35)
        regression, stress = model(batch)
        assert regression.shape == (4, 3)


def test_stress_output_is_logit():
    """Stress output is a raw logit (not bounded to 0-1)."""
    model = DemandLSTM(input_dim=35)
    batch = torch.randn(16, 168, 35)

    _, stress = model(batch)

    # Logits can be any real number, not just 0-1
    # Just verify it's not all zeros (model is doing something)
    assert not torch.all(stress == 0)
