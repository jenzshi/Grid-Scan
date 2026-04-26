"""Tests for ML feature pipeline."""

from datetime import datetime, timezone, timedelta

from backend.ml.feature_pipeline import export_training_data


def _make_snapshots(count=5):
    """Build a list of mock snapshots at 5-min intervals."""
    base = datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc)
    snapshots = []
    for i in range(count):
        ts = base + timedelta(minutes=i * 5)
        snapshots.append({
            "captured_at": ts.isoformat(),
            "forecast_mw": 70000.0,
            "actual_mw": 70000.0 + i * 200,
            "error_mw": i * 200.0,
            "error_pct": (i * 200.0) / 70000.0,
            "reserve_margin_mw": 6000.0 - i * 100,
            "physical_responsive_capability_mw": 5500.0 - i * 50,
            "thermal_outage_mw": 3000.0 + i * 50,
            "reserve_price_adder": 10.0 + i * 2,
            "weather_temp_f": 95.0 + i * 0.5,
            "stress_score": 30.0 + i * 5,
            "wind_actual_mw": 15000.0 - i * 100,
            "wind_forecast_mw": 18000.0,
            "wind_shortfall_mw": 3000.0 + i * 100,
            "solar_actual_mw": 8000.0 - i * 50,
            "solar_forecast_mw": 9000.0,
            "solar_shortfall_mw": 1000.0 + i * 50,
            "gas_generation_mw": 35000.0,
            "nuclear_generation_mw": 5000.0,
            "coal_generation_mw": 7000.0,
            "storage_mw": 2000.0,
        })
    return snapshots


def _make_events():
    """Build a mock event overlapping the test snapshots."""
    base = datetime(2026, 4, 26, 14, 10, tzinfo=timezone.utc)
    return [{
        "detected_at": base.isoformat(),
        "resolved_at": (base + timedelta(minutes=30)).isoformat(),
        "peak_error_pct": 0.06,
        "error_growth_rate_mw_per_hour": 800.0,
    }]


def test_export_returns_same_count():
    """Output has same number of rows as input snapshots."""
    snaps = _make_snapshots(10)
    rows = export_training_data(snaps, [])
    assert len(rows) == 10


def test_empty_input():
    """Empty snapshots returns empty list."""
    assert export_training_data([], []) == []


def test_derived_features_present():
    """Derived features are added to each row."""
    snaps = _make_snapshots(15)
    rows = export_training_data(snaps, [])
    row = rows[-1]
    assert "hour_sin" in row
    assert "hour_cos" in row
    assert "error_mw_mean_1h" in row
    assert "error_mw_std_1h" in row
    assert "error_roc_1h" in row
    assert "error_x_thermal" in row


def test_labels_attached():
    """Event labels are applied to overlapping snapshots."""
    snaps = _make_snapshots(10)
    events = _make_events()
    rows = export_training_data(snaps, events)

    # Snapshot at index 2 (14:10) should be in the event
    assert rows[2]["stress_event_active"] is True
    assert rows[2]["event_severity"] is not None


def test_time_to_event_computed():
    """Pre-event snapshots get time_to_event_minutes."""
    snaps = _make_snapshots(10)
    events = _make_events()
    rows = export_training_data(snaps, events)

    # First snapshot (14:00) is 10 min before event at 14:10
    assert rows[0]["time_to_event_minutes"] == 10.0


def test_rolling_windows_different_sizes():
    """1h, 4h, and 24h rolling windows produce different values."""
    snaps = _make_snapshots(50)
    rows = export_training_data(snaps, [])
    last = rows[-1]
    # 1h window covers 12 snapshots, 4h covers 48 — means should differ
    # when data is monotonically increasing
    assert last["error_mw_mean_1h"] != last["error_mw_mean_4h"]


def test_cyclical_encoding_range():
    """Cyclical time features should be between -1 and 1."""
    snaps = _make_snapshots(5)
    rows = export_training_data(snaps, [])
    for row in rows:
        assert -1.0 <= row["hour_sin"] <= 1.0
        assert -1.0 <= row["hour_cos"] <= 1.0
        assert -1.0 <= row["dow_sin"] <= 1.0
        assert -1.0 <= row["dow_cos"] <= 1.0
