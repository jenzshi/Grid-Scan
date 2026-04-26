"""LSTM model for ERCOT demand prediction."""

import torch
import torch.nn as nn


class DemandLSTM(nn.Module):
    """
    2-layer LSTM for multi-horizon demand prediction.

    Takes a sequence of hourly feature vectors and outputs:
    - 3 regression values: demand at t+1h, t+4h, t+12h
    - 1 binary probability: stress event likelihood

    Architecture: input projection -> 2-layer LSTM -> FC heads.
    """

    def __init__(self, input_dim: int, hidden_dim: int = 128,
                 num_layers: int = 2, dropout: float = 0.2):
        """
        Initialize the LSTM model.

        Args:
            input_dim: Number of features per timestep.
            hidden_dim: LSTM hidden state size.
            num_layers: Number of stacked LSTM layers.
            dropout: Dropout rate between LSTM layers.
        """
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.input_proj = nn.Linear(input_dim, hidden_dim)

        self.lstm = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.dropout = nn.Dropout(dropout)

        # Regression head: 3 demand predictions
        self.regression_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 3),
        )

        # Stress classification head: binary probability
        self.stress_head = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.

        Args:
            x: Input tensor of shape (batch, seq_len, input_dim).

        Returns:
            Tuple of:
                regression: (batch, 3) — predicted demand at t+1h/4h/12h.
                stress: (batch, 1) — stress probability logit.
        """
        projected = self.input_proj(x)
        lstm_out, _ = self.lstm(projected)

        # Use the last timestep's output
        last_hidden = lstm_out[:, -1, :]
        last_hidden = self.dropout(last_hidden)

        regression = self.regression_head(last_hidden)
        stress = self.stress_head(last_hidden)

        return regression, stress

    def count_parameters(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
