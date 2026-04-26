"""Tests for backend.ml.historical_features."""

import numpy as np
import pandas as pd

from backend.ml.historical_features import (
    build_feature_matrix,
    get_feature_columns,
    get_target_columns,
    _add_cyclical_time,
    _add_zone_ratios,
    _add_lagged_load,
    _add_targets,
    _add_calendar,
)


def _make_load_df(n_hours=500):
    """Create a minimal ERCOT load DataFrame for testing."""
    times = pd.date_range("2023-01-01", periods=n_hours, freq="h", tz="UTC")
    base = 50000 + 10000 * np.sin(np.linspace(0, 20 * np.pi, n_hours))
    noise = np.random.default_rng(42).normal(0, 500, n_hours)
    load = base + noise

    df = pd.DataFrame({
        "interval_start": times,
        "ercot": load,
        "coast": load * 0.15,
        "east": load * 0.08,
        "far_west": load * 0.06,
        "north": load * 0.12,
        "north_central": load * 0.25,
        "south_central": load * 0.18,
        "southern": load * 0.10,
        "west": load * 0.06,
    })
    return df


def _make_weather_df(n_hours=500):
    """Create a minimal weather DataFrame for testing."""
    times = pd.date_range("2023-01-01", periods=n_hours, freq="h", tz="UTC")
    return pd.DataFrame({
        "time": times,
        "temperature_f": np.random.default_rng(42).uniform(40, 105, n_hours),
        "humidity_pct": np.random.default_rng(42).uniform(20, 90, n_hours),
        "wind_speed_mph": np.random.default_rng(42).uniform(0, 30, n_hours),
    })


def test_build_feature_matrix_returns_correct_shape():
    """Feature matrix has expected rows and no NaN."""
    load = _make_load_df(500)
    weather = _make_weather_df(500)
    df = build_feature_matrix(load, weather)

    # After dropping 168 warmup + 12 target rows = 320 rows max
    assert len(df) > 0
    assert len(df) <= 500 - 168 - 12

    # No NaN in feature columns
    feat_cols = get_feature_columns(df)
    assert df[feat_cols].isna().sum().sum() == 0


def test_cyclical_features_in_range():
    """Cyclical sin/cos values are in [-1, 1]."""
    load = _make_load_df(48)
    df = pd.DataFrame({
        "interval_start": load["interval_start"],
        "ercot_mw": load["ercot"],
    })
    df = _add_cyclical_time(df)

    for col in ["hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos"]:
        assert df[col].min() >= -1.0
        assert df[col].max() <= 1.0


def test_lagged_load_correct_offset():
    """Lag features have the correct time offset."""
    load = _make_load_df(50)
    df = pd.DataFrame({
        "interval_start": load["interval_start"],
        "ercot_mw": load["ercot"],
    })
    df = _add_lagged_load(df)

    # At index 24, lag_24h should equal ercot_mw at index 0
    assert df.loc[24, "lag_24h"] == df.loc[0, "ercot_mw"]

    # lag_1h at index 10 should equal ercot_mw at index 9
    assert df.loc[10, "lag_1h"] == df.loc[9, "ercot_mw"]


def test_target_shift_correct():
    """Targets are shifted forward by the correct amount."""
    load = _make_load_df(50)
    df = pd.DataFrame({
        "interval_start": load["interval_start"],
        "ercot_mw": load["ercot"],
    })
    df = _add_targets(df)

    # target_1h at index 0 should equal ercot_mw at index 1
    assert df.loc[0, "target_1h"] == df.loc[1, "ercot_mw"]

    # target_4h at index 0 should equal ercot_mw at index 4
    assert df.loc[0, "target_4h"] == df.loc[4, "ercot_mw"]


def test_zone_ratios_sum_to_approximately_one():
    """Zone ratios should sum close to 1.0."""
    load = _make_load_df(50)
    weather = _make_weather_df(50)
    df = build_feature_matrix(load, weather)

    ratio_cols = [c for c in df.columns if c.endswith("_ratio")]
    if ratio_cols:
        row_sums = df[ratio_cols].sum(axis=1)
        assert all(abs(s - 1.0) < 0.01 for s in row_sums)


def test_calendar_features_binary():
    """is_weekend and is_holiday are 0.0 or 1.0."""
    load = _make_load_df(200)
    df = pd.DataFrame({
        "interval_start": load["interval_start"],
        "ercot_mw": load["ercot"],
    })
    df = _add_calendar(df)

    assert set(df["is_weekend"].unique()).issubset({0.0, 1.0})
    assert set(df["is_holiday"].unique()).issubset({0.0, 1.0})


def test_get_target_columns_returns_three():
    """Target columns list has exactly 3 entries."""
    cols = get_target_columns()
    assert len(cols) == 3
    assert "target_1h" in cols
    assert "target_4h" in cols
    assert "target_12h" in cols


def test_get_feature_columns_excludes_targets():
    """Feature columns do not include targets or interval_start."""
    load = _make_load_df(500)
    weather = _make_weather_df(500)
    df = build_feature_matrix(load, weather)
    feat_cols = get_feature_columns(df)

    assert "target_1h" not in feat_cols
    assert "target_4h" not in feat_cols
    assert "target_12h" not in feat_cols
    assert "interval_start" not in feat_cols
    assert "is_stress" not in feat_cols
