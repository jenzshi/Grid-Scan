"""Survival analysis engine — what happened historically in similar conditions."""

import math
import random
from datetime import datetime, timezone

from backend.config import MOCK_MODE, HISTORICAL_FINGERPRINTS
from backend.storage.supabase_client import (
    save_historical_period,
    get_historical_periods,
    historical_archive_exists,
    delete_historical_periods_by_year_season,
)


def ingest_historical_archive() -> None:
    """
    One-time job. Generates synthetic historical periods seeded from
    fingerprinted events. Full ERCOT archive download via gridstatus
    is future work. Safe to re-run — skips years already present.
    """
    existing = get_historical_periods()
    existing_years = {p.get("year") for p in existing}

    # Always try to add fingerprinted periods for missing years
    _ingest_fingerprinted_periods()

    # Only generate synthetic fill if we have fewer than 20 total
    if len(existing) < 20:
        _ingest_synthetic_periods()


def find_similar_periods(current: dict, n: int = 10) -> list[dict]:
    """
    Find the n most similar historical peak periods to current conditions.

    Filters by season first, then ranks by Euclidean distance across
    normalized key metrics.

    Args:
        current: Dict with season, peak_error_pct, thermal_outage_mw,
                 pre_period_planned_outage_mw, reserve_margin_pct.
        n: Number of results to return.

    Returns:
        List of historical_period dicts ranked by similarity.
    """
    season = current.get("season")
    all_periods = get_historical_periods(season=season)

    # If too few same-season matches, include all seasons
    if len(all_periods) < 5:
        all_periods = get_historical_periods()

    scored = []
    for period in all_periods:
        distance = _compute_distance(current, period)
        scored.append((distance, period))

    scored.sort(key=lambda x: x[0])
    return [period for _, period in scored[:n]]


def compute_survival_rate(similar_periods: list[dict]) -> dict:
    """
    Compute outcome breakdown for a set of similar periods.

    Args:
        similar_periods: List of historical period dicts.

    Returns:
        Dict with total, counts by outcome, and failure_rate.
    """
    total = len(similar_periods)
    if total == 0:
        return {
            "total": 0,
            "by_outcome": {},
            "failure_rate": 0.0,
        }

    counts = {}
    for period in similar_periods:
        outcome = period.get("outcome", "normal")
        counts[outcome] = counts.get(outcome, 0) + 1

    failures = counts.get("catastrophic", 0) + counts.get("near_miss", 0)
    failure_rate = failures / total

    return {
        "total": total,
        "by_outcome": counts,
        "failure_rate": round(failure_rate, 3),
    }


def identify_survival_factors(
    failures: list[dict],
    survivals: list[dict],
) -> list[dict]:
    """
    Compare failures vs survivals across metric columns.

    Returns ranked list of factors by magnitude of difference.
    Simple mean comparison — no ML.

    Args:
        failures: Periods with catastrophic or near_miss outcomes.
        survivals: Periods with managed or normal outcomes.

    Returns:
        List of factor dicts with 'field', 'description', 'magnitude'.
    """
    if not failures or not survivals:
        return []

    compare_fields = [
        ("peak_error_pct", "peak forecast error"),
        ("max_thermal_outage_mw", "thermal outages"),
        ("pre_period_planned_outage_mw", "planned outages going into the period"),
        ("min_reserve_margin_pct", "minimum reserve margin"),
    ]

    factors = []
    for field, label in compare_fields:
        fail_vals = _extract_values(failures, field)
        surv_vals = _extract_values(survivals, field)

        if not fail_vals or not surv_vals:
            continue

        fail_mean = sum(fail_vals) / len(fail_vals)
        surv_mean = sum(surv_vals) / len(surv_vals)
        magnitude = _compute_pct_diff(fail_mean, surv_mean)

        description = _build_factor_description(
            label, fail_mean, surv_mean, magnitude, field
        )

        factors.append({
            "field": field,
            "description": description,
            "magnitude": abs(magnitude),
        })

    # Add cause pattern analysis
    cause_factor = _analyze_cause_patterns(failures, survivals)
    if cause_factor:
        factors.append(cause_factor)

    factors.sort(key=lambda f: f["magnitude"], reverse=True)
    return factors


def build_history_response(current: dict) -> dict:
    """
    Orchestrate the full survival analysis for /api/ercot/history.

    Args:
        current: Current conditions dict.

    Returns:
        Structured response dict for the frontend.
    """
    similar = find_similar_periods(current, n=15)
    survival = compute_survival_rate(similar)

    failures = [
        p for p in similar
        if p.get("outcome") in ("catastrophic", "near_miss")
    ]
    survivals = [
        p for p in similar
        if p.get("outcome") in ("managed", "normal")
    ]

    factors = identify_survival_factors(failures, survivals)

    summary = _build_survival_summary(survival)
    condition_desc = _build_condition_description(current)

    pattern_threads = _build_pattern_threads()
    counterfactual = _build_counterfactual(failures, survivals)

    return {
        "condition_description": condition_desc,
        "survival_summary": summary,
        "similar_periods": [_format_period(p) for p in similar],
        "survival_rate": survival,
        "survival_factors": factors,
        "pattern_threads": pattern_threads,
        "counterfactual": counterfactual,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_pattern_threads() -> list[dict]:
    """
    Build narrative threads linking related historical events.

    Draws from HISTORICAL_FINGERPRINTS to identify causal chains —
    the same root cause recurring across decades.

    Returns:
        List of thread dicts with title, events, and narrative.
    """
    threads = []

    # Winterization thread: 1989 -> 2011 -> 2021
    winter_keys = ["freeze_1989", "groundhog_day_2011", "uri_feb_2021"]
    winter_events = []
    for key in winter_keys:
        fp = HISTORICAL_FINGERPRINTS.get(key)
        if fp:
            winter_events.append({
                "key": key,
                "label": fp["label"],
                "outcome": fp["outcome"],
                "load_shed_mw": fp.get("load_shed_mw"),
                "customers_affected": fp.get("customers_affected"),
                "notes": fp.get("notes"),
            })

    if winter_events:
        threads.append({
            "title": "The Winterization Thread: 1989 \u2192 2011 \u2192 2021",
            "type": "catastrophic_chain",
            "events": winter_events,
            "narrative": (
                "Three catastrophic winter failures spanning 32 years, all caused "
                "by the same root failure: unprotected generating equipment freezing "
                "under extreme cold. After each event, regulators issued winterization "
                "recommendations. After each event, those recommendations were ignored. "
                "The 1989 freeze led to PUCT recommendations. The 2011 Groundhog Day "
                "Blizzard triggered FERC/NERC recommendations. Neither set was acted upon. "
                "Uri in 2021 — the worst grid failure in US history — was the direct, "
                "predictable consequence. 4.5 million customers lost power. The grid came "
                "within 4 minutes and 37 seconds of total uncontrolled collapse."
            ),
        })

    # Maintenance deferral thread
    maint_keys = ["spring_apr_2006", "summer_may_jun_2022", "summer_jun_2021"]
    maint_events = []
    for key in maint_keys:
        fp = HISTORICAL_FINGERPRINTS.get(key)
        if fp:
            maint_events.append({
                "key": key,
                "label": fp["label"],
                "outcome": fp["outcome"],
                "notes": fp.get("notes"),
            })

    if maint_events:
        threads.append({
            "title": "Maintenance Deferral: The Hidden Risk Multiplier",
            "type": "structural_pattern",
            "events": maint_events,
            "narrative": (
                "Spring 2006: 14,500 MW in planned maintenance left the grid exposed "
                "when an unexpected April heat wave hit. Rolling blackouts followed. "
                "May 2022: ERCOT asked plants to delay scheduled maintenance — 6 of "
                "those plants then tripped simultaneously under load. June 2021: "
                "Uri-damaged plants still failing 4 months later created a rare summer "
                "supply-side squeeze. The pattern is clear: high planned outages entering "
                "a stress period is itself a leading indicator of catastrophic risk."
            ),
        })

    # Elliott contrast thread
    elliott = HISTORICAL_FINGERPRINTS.get("elliott_dec_2022")
    uri = HISTORICAL_FINGERPRINTS.get("uri_feb_2021")
    if elliott and uri:
        threads.append({
            "title": "The Elliott Contrast: Why 2022 Survived When 2021 Didn't",
            "type": "contrast",
            "events": [
                {
                    "key": "uri_feb_2021",
                    "label": uri["label"],
                    "outcome": uri["outcome"],
                    "notes": uri.get("notes"),
                },
                {
                    "key": "elliott_dec_2022",
                    "label": elliott["label"],
                    "outcome": elliott["outcome"],
                    "notes": elliott.get("notes"),
                },
            ],
            "narrative": (
                "Winter Storm Elliott (Dec 2022) hit with a 6,702 MW forecast error "
                "and 10,000 MW of thermal outages — conditions that looked dangerous. "
                "But PRC never fell below 4,052 MW. Zero load shed. Zero customers "
                "affected. The critical difference: only 4 of 255 inspected units had "
                "weather-related outages, vs. 58% gas-fired failures during Uri. "
                "Post-Uri winterization reforms worked. Elliott proves that error "
                "magnitude alone does not predict catastrophe — response capacity is "
                "what separates survival from failure."
            ),
        })

    # Post-reform resilience thread: 2022-2025 improvements
    reform_events = []
    for key in ["elliott_dec_2022", "winter_heather_jan_2024",
                "summer_aug_2024", "summer_2025"]:
        fp = HISTORICAL_FINGERPRINTS.get(key)
        if fp:
            reform_events.append({
                "key": key,
                "label": fp["label"],
                "outcome": fp["outcome"],
                "notes": fp.get("notes"),
            })

    if len(reform_events) >= 2:
        threads.append({
            "title": "Post-Uri Reforms: The Evidence They're Working",
            "type": "contrast",
            "events": reform_events,
            "narrative": (
                "Since Uri, ERCOT has weathered increasingly extreme conditions "
                "without catastrophic failure. Winter Storm Heather (Jan 2024) "
                "set a new all-time winter peak of 78,349 MW — thermal outages "
                "were half of Elliott's and a quarter of Uri's. Summer 2024 broke "
                "the all-time demand record at 85,559 MW with zero conservation "
                "appeals. Summer 2025 was the first since Uri where ERCOT never "
                "asked customers to conserve. Battery storage nearly doubled, "
                "solar broke 17 records. The generation-side reforms are working."
            ),
        })

    # Fern warning thread: growing structural risk
    fern = HISTORICAL_FINGERPRINTS.get("winter_fern_jan_2026")
    if fern:
        threads.append({
            "title": "Winter Storm Fern: The Grid Held — But Margins Are Shrinking",
            "type": "structural_pattern",
            "events": [{
                "key": "winter_fern_jan_2026",
                "label": fern["label"],
                "outcome": fern["outcome"],
                "notes": fern.get("notes"),
            }],
            "narrative": (
                "Winter Storm Fern (Jan 2026) required a DOE emergency order "
                "authorizing backup generation at data centers. The grid held — "
                "no EEA, no rolling blackouts. But reserve margins have dropped "
                "to 10.1% from 17.5% in 2021. Winter peak demand is up 20% "
                "since Uri while dispatchable generation capacity remains roughly "
                "flat. In 2025 alone, ERCOT received 225 new large load connection "
                "requests — three-quarters from data centers. The generation-side "
                "reforms are working, but demand growth is outpacing them. The next "
                "Uri-scale storm will test whether the margin is still sufficient."
            ),
        })

    return threads


def _build_counterfactual(
    failures: list[dict], survivals: list[dict]
) -> list[str]:
    """
    Generate 'what would need to change' statements by comparing
    failure conditions to survival conditions.

    Args:
        failures: Periods with catastrophic or near_miss outcomes.
        survivals: Periods with managed or normal outcomes.

    Returns:
        List of plain-language counterfactual statements.
    """
    if not failures or not survivals:
        return []

    statements = []

    fail_outages = _extract_values(failures, "pre_period_planned_outage_mw")
    surv_outages = _extract_values(survivals, "pre_period_planned_outage_mw")
    if fail_outages and surv_outages:
        fail_avg = sum(fail_outages) / len(fail_outages)
        surv_avg = sum(surv_outages) / len(surv_outages)
        if fail_avg > surv_avg * 1.2:
            pct_diff = round((fail_avg - surv_avg) / fail_avg * 100)
            statements.append(
                f"If planned outages had been {pct_diff}% lower going into "
                f"stress periods, conditions would match the survival profile "
                f"({surv_avg:,.0f} MW vs {fail_avg:,.0f} MW in failures)."
            )

    fail_errors = _extract_values(failures, "peak_error_pct")
    surv_errors = _extract_values(survivals, "peak_error_pct")
    if fail_errors and surv_errors:
        fail_avg = sum(fail_errors) / len(fail_errors)
        surv_avg = sum(surv_errors) / len(surv_errors)
        if fail_avg > surv_avg * 1.3:
            statements.append(
                f"Forecast accuracy would need to improve from "
                f"{fail_avg * 100:.1f}% error to below {surv_avg * 100:.1f}% "
                f"to match conditions that historically resolved safely."
            )

    fail_reserves = _extract_values(failures, "min_reserve_margin_pct")
    surv_reserves = _extract_values(survivals, "min_reserve_margin_pct")
    if fail_reserves and surv_reserves:
        fail_avg = sum(fail_reserves) / len(fail_reserves)
        surv_avg = sum(surv_reserves) / len(surv_reserves)
        if surv_avg > fail_avg * 1.3:
            statements.append(
                f"Maintaining reserve margins above {surv_avg * 100:.1f}% "
                f"(vs {fail_avg * 100:.1f}% in failures) is the threshold "
                f"that historically separated survival from catastrophe."
            )

    # Cause pattern counterfactual
    fail_supply = sum(
        1 for p in failures
        if p.get("cause_classification") == "supply_side"
    )
    if fail_supply > len(failures) * 0.5:
        statements.append(
            "Preventing supply-side cascades (generator trips, fuel failures) "
            "is the single highest-leverage intervention — the majority of "
            "catastrophic failures were supply-driven, not demand-driven."
        )

    return statements


def _compute_distance(current: dict, period: dict) -> float:
    """
    Euclidean distance between current conditions and a historical period.

    Args:
        current: Current conditions dict.
        period: Historical period dict.

    Returns:
        Distance value (lower = more similar).
    """
    fields = [
        ("peak_error_pct", 0.20),
        ("max_thermal_outage_mw", 30000.0),
        ("pre_period_planned_outage_mw", 15000.0),
        ("min_reserve_margin_pct", 0.30),
    ]

    # Map current keys to period keys
    key_map = {
        "peak_error_pct": "peak_error_pct",
        "thermal_outage_mw": "max_thermal_outage_mw",
        "pre_period_planned_outage_mw": "pre_period_planned_outage_mw",
        "reserve_margin_pct": "min_reserve_margin_pct",
    }

    sum_sq = 0.0
    matched = 0

    for field, scale in fields:
        # Try current dict with its own keys first, then mapped keys
        current_key = None
        for ck, pk in key_map.items():
            if pk == field:
                current_key = ck
                break

        current_val = current.get(current_key) or current.get(field)
        period_val = period.get(field)

        if current_val is None or period_val is None:
            continue

        normalized_diff = (current_val - period_val) / scale
        sum_sq += normalized_diff ** 2
        matched += 1

    if matched == 0:
        return float("inf")

    return math.sqrt(sum_sq / matched)


def _extract_values(periods: list[dict], field: str) -> list[float]:
    """Extract non-None numeric values for a field from period list."""
    values = []
    for p in periods:
        val = p.get(field)
        if val is not None and isinstance(val, (int, float)):
            values.append(val)
    return values


def _compute_pct_diff(fail_mean: float, surv_mean: float) -> float:
    """Compute percentage difference between failure and survival means."""
    baseline = max(abs(surv_mean), 0.001)
    return (fail_mean - surv_mean) / baseline


def _build_factor_description(
    label: str,
    fail_mean: float,
    surv_mean: float,
    magnitude: float,
    field: str,
) -> str:
    """Build a plain-language factor description."""
    pct = abs(magnitude) * 100
    direction = "higher" if fail_mean > surv_mean else "lower"

    if field.endswith("_pct"):
        fail_display = f"{fail_mean * 100:.1f}%"
        surv_display = f"{surv_mean * 100:.1f}%"
    elif field.endswith("_mw"):
        fail_display = f"{fail_mean:,.0f} MW"
        surv_display = f"{surv_mean:,.0f} MW"
    else:
        fail_display = f"{fail_mean:.2f}"
        surv_display = f"{surv_mean:.2f}"

    return (
        f"Failures had {pct:.0f}% {direction} {label} "
        f"({fail_display} vs {surv_display} in survivals)"
    )


def _analyze_cause_patterns(
    failures: list[dict],
    survivals: list[dict],
) -> dict | None:
    """Analyze cause classification patterns between groups."""
    fail_supply = sum(
        1 for p in failures
        if p.get("cause_classification") == "supply_side"
    )
    surv_supply = sum(
        1 for p in survivals
        if p.get("cause_classification") == "supply_side"
    )

    if not failures:
        return None

    fail_pct = fail_supply / len(failures)
    surv_pct = surv_supply / len(survivals) if survivals else 0

    if abs(fail_pct - surv_pct) < 0.1:
        return None

    fail_count = len(failures)
    surv_count = len(survivals)

    return {
        "field": "cause_classification",
        "description": (
            f"{fail_supply} of {fail_count} failures were supply-side vs "
            f"{surv_supply} of {surv_count} survivals — supply-side events "
            f"are more likely to cascade into catastrophic failure"
        ),
        "magnitude": abs(fail_pct - surv_pct) * 100,
    }


def _build_survival_summary(survival: dict) -> str:
    """Build the plain-text survival summary for the frontend."""
    total = survival["total"]
    if total == 0:
        return "No similar historical periods found."

    by_outcome = survival["by_outcome"]
    normal = by_outcome.get("normal", 0) + by_outcome.get("managed", 0)
    near_miss = by_outcome.get("near_miss", 0)
    catastrophic = by_outcome.get("catastrophic", 0)
    safe_pct = round(normal / total * 100)

    parts = [f"In {total} similar historical periods since 2003"]
    parts.append(f", {normal} resolved without incident ({safe_pct}%).")

    if near_miss:
        parts.append(f" {near_miss} became near-misses.")
    if catastrophic:
        parts.append(f" {catastrophic} became catastrophic.")

    return "".join(parts)


def _build_condition_description(current: dict) -> str:
    """Build a one-line description of the conditions being matched."""
    season = current.get("season", "unknown")
    error_pct = current.get("peak_error_pct", 0)
    return (
        f"{season.capitalize()} conditions with "
        f"{error_pct * 100:.1f}% forecast error"
    )


def _format_period(period: dict) -> dict:
    """Format a historical period for frontend display."""
    return {
        "year": period.get("year"),
        "season": period.get("season"),
        "peak_error_pct": period.get("peak_error_pct"),
        "peak_actual_mw": period.get("peak_actual_mw"),
        "max_thermal_outage_mw": period.get("max_thermal_outage_mw"),
        "min_reserve_margin_pct": period.get("min_reserve_margin_pct"),
        "outcome": period.get("outcome"),
        "notes": period.get("notes"),
    }


# ---------------------------------------------------------------------------
# Mock ingestion — synthetic historical periods
# ---------------------------------------------------------------------------

def _ingest_mock_archive():
    """Generate 40-50 synthetic historical periods spanning 2003-2025."""
    # First, add fingerprinted events as known periods
    _ingest_fingerprinted_periods()
    # Then fill remaining years with plausible data
    _ingest_synthetic_periods()


def _ingest_fingerprinted_periods():
    """Convert fingerprinted events to historical period rows."""
    fp_periods = [
        {
            "year": 2021, "season": "winter",
            "peak_actual_mw": 69150, "peak_forecast_mw": 57699,
            "peak_error_mw": 11451, "peak_error_pct": 0.199,
            "max_thermal_outage_mw": 28000,
            "min_reserve_margin_pct": 0.0,
            "pre_period_planned_outage_mw": 11500,
            "cause_classification": "supply_side",
            "outcome": "catastrophic", "outcome_source": "labeled",
            "notes": "Winter Storm Uri",
        },
        {
            "year": 2011, "season": "winter",
            "peak_actual_mw": 57000, "peak_forecast_mw": 52000,
            "peak_error_mw": 5000, "peak_error_pct": 0.096,
            "max_thermal_outage_mw": 14000,
            "min_reserve_margin_pct": 0.0,
            "pre_period_planned_outage_mw": 11500,
            "cause_classification": "supply_side",
            "outcome": "catastrophic", "outcome_source": "labeled",
            "notes": "Groundhog Day Blizzard",
        },
        {
            "year": 2006, "season": "spring",
            "peak_actual_mw": 53000, "peak_forecast_mw": 49000,
            "peak_error_mw": 4000, "peak_error_pct": 0.082,
            "max_thermal_outage_mw": 2440,
            "min_reserve_margin_pct": 0.02,
            "pre_period_planned_outage_mw": 14500,
            "cause_classification": "mixed",
            "outcome": "catastrophic", "outcome_source": "labeled",
            "notes": "Spring Heat Surprise — April 2006",
        },
        {
            "year": 2022, "season": "winter",
            "peak_actual_mw": 74100, "peak_forecast_mw": 67398,
            "peak_error_mw": 6702, "peak_error_pct": 0.099,
            "max_thermal_outage_mw": 10000,
            "min_reserve_margin_pct": 0.05,
            "pre_period_planned_outage_mw": 4000,
            "cause_classification": "demand_side",
            "outcome": "near_miss", "outcome_source": "labeled",
            "notes": "Winter Storm Elliott",
        },
        {
            "year": 2023, "season": "summer",
            "peak_actual_mw": 85464, "peak_forecast_mw": 82000,
            "peak_error_mw": 3464, "peak_error_pct": 0.042,
            "max_thermal_outage_mw": 5000,
            "min_reserve_margin_pct": 0.08,
            "pre_period_planned_outage_mw": 3000,
            "cause_classification": "demand_side",
            "outcome": "managed", "outcome_source": "labeled",
            "notes": "Summer Evening Stress 2023",
        },
        {
            "year": 2024, "season": "winter",
            "peak_actual_mw": 78349, "peak_forecast_mw": 74000,
            "peak_error_mw": 4349, "peak_error_pct": 0.059,
            "max_thermal_outage_mw": 7000,
            "min_reserve_margin_pct": 0.09,
            "pre_period_planned_outage_mw": 4000,
            "cause_classification": "demand_side",
            "outcome": "managed", "outcome_source": "labeled",
            "notes": (
                "Winter Storm Heather — all-time winter peak 78,349 MW. "
                "First full winter with weatherization rules. Thermal outages "
                "~7,000 MW — half of Elliott. Conservation appeals issued, no EEA."
            ),
        },
        {
            "year": 2024, "season": "summer",
            "peak_actual_mw": 85559, "peak_forecast_mw": 83000,
            "peak_error_mw": 2559, "peak_error_pct": 0.031,
            "max_thermal_outage_mw": 4000,
            "min_reserve_margin_pct": 0.12,
            "pre_period_planned_outage_mw": 3000,
            "cause_classification": "demand_side",
            "outcome": "normal", "outcome_source": "labeled",
            "notes": (
                "All-time ERCOT record 85,559 MW. Zero conservation appeals "
                "all summer. Battery storage + solar additions closed the gap. "
                "Sixth-hottest summer on record."
            ),
        },
        {
            "year": 2025, "season": "summer",
            "peak_actual_mw": 86000, "peak_forecast_mw": 84000,
            "peak_error_mw": 2000, "peak_error_pct": 0.024,
            "max_thermal_outage_mw": 3500,
            "min_reserve_margin_pct": 0.13,
            "pre_period_planned_outage_mw": 2800,
            "cause_classification": "demand_side",
            "outcome": "normal", "outcome_source": "labeled",
            "notes": (
                "First time since Uri that ERCOT never asked customers to "
                "conserve. Solar broke 17 records. Battery storage nearly "
                "doubled. EEA probability dropped to 3%."
            ),
        },
        {
            "year": 2026, "season": "winter",
            "peak_actual_mw": 84000, "peak_forecast_mw": 80000,
            "peak_error_mw": 4000, "peak_error_pct": 0.050,
            "max_thermal_outage_mw": 7800,
            "min_reserve_margin_pct": 0.101,
            "pre_period_planned_outage_mw": 5000,
            "cause_classification": "mixed",
            "outcome": "near_miss", "outcome_source": "labeled",
            "notes": (
                "Winter Storm Fern — DOE emergency order issued. 21,784 MW "
                "total outages. Grid held, no EEA. But reserve margin down to "
                "10.1% from 17.5% in 2021. Data center demand a growing threat."
            ),
        },
    ]

    existing = get_historical_periods()
    existing_labeled = set()
    existing_any = set()
    for ep in existing:
        key = (ep.get("year"), ep.get("season"))
        existing_any.add(key)
        if ep.get("outcome_source") == "labeled":
            existing_labeled.add(key)

    for p in fp_periods:
        key = (p["year"], p["season"])
        if key in existing_labeled:
            continue
        # Delete synthetic entries before inserting labeled ones
        if key in existing_any:
            delete_historical_periods_by_year_season(p["year"], p["season"])
        p["period_start"] = f"{p['year']}-01-01T00:00:00+00:00"
        p["period_end"] = f"{p['year']}-12-31T00:00:00+00:00"
        save_historical_period(p)


def _ingest_synthetic_periods():
    """Fill remaining years with synthetic normal/managed periods."""
    existing_years = set()
    for p in get_historical_periods():
        existing_years.add(p.get("year"))

    for year in range(2003, 2027):
        for season in ("summer", "winter"):
            key = (year, season)
            if year in existing_years:
                continue

            # Most periods are normal
            outcome_roll = random.random()
            if outcome_roll < 0.05:
                outcome = "near_miss"
            elif outcome_roll < 0.15:
                outcome = "managed"
            else:
                outcome = "normal"

            base_demand = 65000 + (year - 2003) * 500
            if season == "summer":
                base_demand += 10000

            error_pct = random.uniform(0.01, 0.04)
            if outcome == "near_miss":
                error_pct = random.uniform(0.06, 0.10)
            elif outcome == "managed":
                error_pct = random.uniform(0.03, 0.06)

            forecast = base_demand
            actual = forecast * (1 + error_pct)
            outage = random.uniform(2000, 5000)
            if outcome == "near_miss":
                outage = random.uniform(6000, 12000)

            reserve = random.uniform(0.10, 0.20)
            if outcome == "near_miss":
                reserve = random.uniform(0.04, 0.08)
            elif outcome == "managed":
                reserve = random.uniform(0.07, 0.12)

            planned = random.uniform(2000, 5000)
            if season == "winter":
                planned = random.uniform(3000, 8000)

            period = {
                "period_start": f"{year}-01-01T00:00:00+00:00",
                "period_end": f"{year}-12-31T00:00:00+00:00",
                "season": season,
                "year": year,
                "peak_actual_mw": round(actual),
                "peak_forecast_mw": round(forecast),
                "peak_error_mw": round(actual - forecast),
                "peak_error_pct": round(error_pct, 4),
                "max_thermal_outage_mw": round(outage),
                "min_reserve_margin_pct": round(reserve, 4),
                "pre_period_planned_outage_mw": round(planned),
                "cause_classification": "demand_side",
                "response_lag_minutes": None,
                "outcome": outcome,
                "outcome_source": "inferred",
                "notes": None,
            }
            save_historical_period(period)

        existing_years.add(year)
