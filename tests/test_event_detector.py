"""Tests for event_detector module."""

import backend.analysis.event_detector as ed


def _reset_state():
    """Reset module-level state between tests."""
    ed._active_event_id = None
    ed._active_event_peak_error_mw = 0.0
    ed._active_event_peak_error_pct = 0.0
    ed._resolve_count = 0


def _make_snapshot(error_pct=0.03, error_mw=2000.0, cause="demand_side"):
    """Build a minimal snapshot dict."""
    return {
        "error_pct": error_pct,
        "error_mw": error_mw,
        "cause": cause,
        "forecast_mw": 70000.0,
        "actual_mw": 70000.0 + error_mw,
    }


def test_no_event_below_threshold():
    """Low error should not trigger an event."""
    _reset_state()
    snap = _make_snapshot(error_pct=0.03, error_mw=2100.0)
    result = ed.detect_event(snap, growth_rate=500.0)
    assert result is None


def test_event_created_on_high_error():
    """Error above threshold creates a new event."""
    _reset_state()
    snap = _make_snapshot(error_pct=0.06, error_mw=4200.0)
    result = ed.detect_event(snap, growth_rate=500.0)
    assert result is not None
    assert result["peak_error_mw"] == 4200.0
    assert result["cause"] == "demand_side"


def test_event_created_on_high_growth():
    """High growth rate alone triggers event."""
    _reset_state()
    snap = _make_snapshot(error_pct=0.03, error_mw=2100.0)
    result = ed.detect_event(snap, growth_rate=1200.0)
    assert result is not None


def test_no_duplicate_event_while_active():
    """Second dangerous snapshot should not create another event."""
    _reset_state()
    snap1 = _make_snapshot(error_pct=0.06, error_mw=4200.0)
    ed.detect_event(snap1, growth_rate=500.0)

    snap2 = _make_snapshot(error_pct=0.08, error_mw=5600.0)
    result = ed.detect_event(snap2, growth_rate=800.0)
    assert result is None


def test_peak_tracking_during_active_event():
    """Peaks should update during active event."""
    _reset_state()
    snap1 = _make_snapshot(error_pct=0.06, error_mw=4200.0)
    ed.detect_event(snap1, growth_rate=500.0)

    snap2 = _make_snapshot(error_pct=0.09, error_mw=6300.0)
    ed.detect_event(snap2, growth_rate=800.0)

    peaks = ed.get_active_event_peaks()
    assert peaks["peak_error_mw"] == 6300.0
    assert peaks["peak_error_pct"] == 0.09


def test_resolution_requires_multiple_cycles():
    """Event should not resolve after just one calm cycle."""
    _reset_state()
    snap1 = _make_snapshot(error_pct=0.06, error_mw=4200.0)
    ed.detect_event(snap1, growth_rate=500.0)

    calm = _make_snapshot(error_pct=0.01, error_mw=700.0)
    resolved = ed.check_event_resolution(calm, growth_rate=100.0)
    assert resolved is False


def test_resolution_after_sustained_calm():
    """Event resolves after enough calm cycles."""
    _reset_state()
    snap1 = _make_snapshot(error_pct=0.06, error_mw=4200.0)
    ed.detect_event(snap1, growth_rate=500.0)

    calm = _make_snapshot(error_pct=0.01, error_mw=700.0)
    ed.check_event_resolution(calm, growth_rate=100.0)
    resolved = ed.check_event_resolution(calm, growth_rate=100.0)
    assert resolved is True
    assert ed.get_active_event_id() is None


def test_resolution_resets_on_spike():
    """A spike during resolution resets the calm counter."""
    _reset_state()
    snap1 = _make_snapshot(error_pct=0.06, error_mw=4200.0)
    ed.detect_event(snap1, growth_rate=500.0)

    calm = _make_snapshot(error_pct=0.01, error_mw=700.0)
    ed.check_event_resolution(calm, growth_rate=100.0)

    # Spike interrupts
    spike = _make_snapshot(error_pct=0.04, error_mw=2800.0)
    ed.check_event_resolution(spike, growth_rate=800.0)

    # Need 2 more calm cycles now
    ed.check_event_resolution(calm, growth_rate=100.0)
    resolved = ed.check_event_resolution(calm, growth_rate=100.0)
    assert resolved is True
