"""Tests for backend.analysis.historical_analysis."""

from backend.analysis.historical_analysis import (
    ingest_historical_archive,
    find_similar_periods,
    compute_survival_rate,
    identify_survival_factors,
    build_history_response,
)
from backend.storage.supabase_client import (
    get_historical_periods,
    historical_archive_exists,
)
from tests.conftest import mock_historical_period


def test_find_similar_periods_filters_by_season():
    """Summer conditions should not return winter periods."""
    ingest_historical_archive()
    current = {
        "season": "summer",
        "peak_error_pct": 0.05,
        "thermal_outage_mw": 4000,
        "pre_period_planned_outage_mw": 3000,
        "reserve_margin_pct": 0.12,
    }
    results = find_similar_periods(current, n=10)
    for period in results:
        assert period["season"] == "summer"


def test_find_similar_periods_returns_n_results():
    """Returns at most n results sorted by similarity."""
    ingest_historical_archive()
    current = {
        "season": "summer",
        "peak_error_pct": 0.04,
        "thermal_outage_mw": 3500,
        "pre_period_planned_outage_mw": 3000,
        "reserve_margin_pct": 0.12,
    }
    results = find_similar_periods(current, n=5)
    assert len(results) <= 5


def test_compute_survival_rate_counts_outcomes():
    """Correctly counts outcomes across a mixed list."""
    periods = [
        {"outcome": "normal"},
        {"outcome": "normal"},
        {"outcome": "managed"},
        {"outcome": "near_miss"},
        {"outcome": "catastrophic"},
    ]
    result = compute_survival_rate(periods)
    assert result["total"] == 5
    assert result["by_outcome"]["normal"] == 2
    assert result["by_outcome"]["catastrophic"] == 1
    assert result["failure_rate"] == 0.4


def test_identify_survival_factors_returns_sorted():
    """Factors are sorted by magnitude of difference."""
    failures = [
        {
            "peak_error_pct": 0.15,
            "max_thermal_outage_mw": 20000,
            "pre_period_planned_outage_mw": 12000,
            "min_reserve_margin_pct": 0.02,
            "cause_classification": "supply_side",
        },
    ]
    survivals = [
        {
            "peak_error_pct": 0.03,
            "max_thermal_outage_mw": 4000,
            "pre_period_planned_outage_mw": 3000,
            "min_reserve_margin_pct": 0.15,
            "cause_classification": "demand_side",
        },
    ]
    factors = identify_survival_factors(failures, survivals)
    assert len(factors) > 0
    magnitudes = [f["magnitude"] for f in factors]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_ingest_is_idempotent():
    """Running ingest twice does not duplicate data."""
    ingest_historical_archive()
    count_first = len(get_historical_periods())
    ingest_historical_archive()
    count_second = len(get_historical_periods())
    assert count_first == count_second


def test_build_history_response_returns_expected_keys():
    """Response has all required top-level keys."""
    ingest_historical_archive()
    current = {
        "season": "summer",
        "peak_error_pct": 0.05,
        "thermal_outage_mw": 4000,
        "pre_period_planned_outage_mw": 3000,
        "reserve_margin_pct": 0.12,
    }
    response = build_history_response(current)
    assert "condition_description" in response
    assert "survival_summary" in response
    assert "similar_periods" in response
    assert "survival_rate" in response
    assert "survival_factors" in response
