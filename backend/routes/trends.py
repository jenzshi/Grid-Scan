"""GET /api/ercot/trends — aggregated trend data for charts."""

from fastapi import APIRouter

from backend.config import HISTORICAL_FINGERPRINTS
from backend.storage.supabase_client import (
    get_trend_aggregates,
    get_recent_snapshots,
    get_historical_periods,
)

router = APIRouter(prefix="/api/ercot", tags=["trends"])


@router.get("/trends")
def get_trends():
    """Return aggregated trend data for the trends view."""
    aggregates = get_trend_aggregates()
    snapshots = get_recent_snapshots(hours=24)
    historical = get_historical_periods()

    stress_scores = _extract_stress_scores(snapshots)
    lag_trend = _compute_lag_trend(aggregates["avg_response_lag_by_month"])
    historical_analysis = _analyze_historical(historical)
    insight_statements = _generate_insight_statements(historical)
    fp_narratives = _build_fingerprint_narratives(historical_analysis)

    return {
        "stress_scores": stress_scores,
        "monthly_events": aggregates["monthly_events"],
        "avg_response_lag_by_month": aggregates["avg_response_lag_by_month"],
        "cause_breakdown": aggregates["cause_breakdown"],
        "lag_trend_direction": lag_trend,
        "historical": historical_analysis,
        "insight_statements": insight_statements,
        "fingerprint_narratives": fp_narratives,
    }


def _extract_stress_scores(snapshots: list[dict]) -> dict:
    """Build a time-keyed dict of stress scores from snapshots."""
    scores = {}
    for snap in snapshots:
        key = snap.get("captured_at", "")[:16]
        score = snap.get("stress_score")
        if score is not None:
            scores[key] = score
    return scores


def _compute_lag_trend(avg_lag_by_month: dict) -> str:
    """Determine if response lag is improving or worsening."""
    if len(avg_lag_by_month) < 2:
        return "stable"

    sorted_months = sorted(avg_lag_by_month.keys())
    recent = avg_lag_by_month[sorted_months[-1]]
    prior_values = [avg_lag_by_month[m] for m in sorted_months[:-1]]
    prior_avg = sum(prior_values) / len(prior_values)

    if recent < prior_avg * 0.9:
        return "improving"
    if recent > prior_avg * 1.1:
        return "worsening"
    return "stable"


def _analyze_historical(periods: list[dict]) -> dict:
    """Analyze 30 years of historical periods for trend insights."""
    if not periods:
        return {}

    # Outcome counts by decade
    by_decade = {}
    for p in periods:
        year = p.get("year", 0)
        decade = f"{(year // 10) * 10}s"
        by_decade.setdefault(decade, {"total": 0, "failures": 0, "periods": []})
        by_decade[decade]["total"] += 1
        by_decade[decade]["periods"].append(p)
        if p.get("outcome") in ("catastrophic", "near_miss"):
            by_decade[decade]["failures"] += 1

    # Error by year for chart
    error_by_year = {}
    for p in periods:
        year = p.get("year")
        pct = p.get("peak_error_pct")
        if year and pct is not None:
            key = str(year)
            if key not in error_by_year or pct > error_by_year[key]:
                error_by_year[key] = round(pct * 100, 2)

    # Outages by year
    outage_by_year = {}
    for p in periods:
        year = p.get("year")
        mw = p.get("max_thermal_outage_mw")
        if year and mw is not None:
            key = str(year)
            if key not in outage_by_year or mw > outage_by_year[key]:
                outage_by_year[key] = round(mw)

    # Outcome distribution
    outcomes = {}
    for p in periods:
        o = p.get("outcome", "normal")
        outcomes[o] = outcomes.get(o, 0) + 1

    # Season breakdown
    season_risk = {}
    for p in periods:
        season = p.get("season", "unknown")
        season_risk.setdefault(season, {"total": 0, "failures": 0})
        season_risk[season]["total"] += 1
        if p.get("outcome") in ("catastrophic", "near_miss"):
            season_risk[season]["failures"] += 1

    # Cause vs outcome
    supply_periods = [p for p in periods if p.get("cause_classification") == "supply_side"]
    demand_periods = [p for p in periods if p.get("cause_classification") == "demand_side"]
    supply_fail = sum(1 for p in supply_periods if p.get("outcome") in ("catastrophic", "near_miss"))
    demand_fail = sum(1 for p in demand_periods if p.get("outcome") in ("catastrophic", "near_miss"))

    # Key events timeline — include labeled events with notes
    notable = []
    seen_keys = set()
    for p in periods:
        has_notes = p.get("notes") and len(p.get("notes", "")) > 10
        is_labeled = p.get("outcome_source") == "labeled"
        is_notable_outcome = p.get("outcome") in ("catastrophic", "near_miss")
        if has_notes and (is_notable_outcome or is_labeled):
            dedup_key = (p.get("year"), p.get("season"))
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            notable.append({
                "year": p.get("year"),
                "season": p.get("season"),
                "outcome": p.get("outcome"),
                "notes": p.get("notes"),
                "peak_error_pct": p.get("peak_error_pct"),
                "max_thermal_outage_mw": p.get("max_thermal_outage_mw"),
            })
    notable.sort(key=lambda x: x.get("year", 0))

    return {
        "total_periods": len(periods),
        "year_range": f"{min(p.get('year', 9999) for p in periods)}-{max(p.get('year', 0) for p in periods)}",
        "outcomes": outcomes,
        "error_by_year": error_by_year,
        "outage_by_year": outage_by_year,
        "season_risk": season_risk,
        "supply_side": {"total": len(supply_periods), "failures": supply_fail},
        "demand_side": {"total": len(demand_periods), "failures": demand_fail},
        "notable_events": notable,
        "by_decade": {k: {"total": v["total"], "failures": v["failures"]} for k, v in by_decade.items()},
    }


def _generate_insight_statements(periods: list[dict]) -> list[str]:
    """
    Generate 4-5 plain-text key findings from historical data.

    Args:
        periods: All historical period dicts.

    Returns:
        List of insight statement strings.
    """
    if not periods:
        return []

    statements = []

    # Insight: catastrophic failures and error thresholds
    catastrophic = [
        p for p in periods if p.get("outcome") == "catastrophic"
    ]
    if catastrophic:
        errors = [
            p["peak_error_pct"] for p in catastrophic
            if p.get("peak_error_pct") is not None
        ]
        if errors:
            min_err = min(errors) * 100
            statements.append(
                f"All {len(catastrophic)} catastrophic failures exceeded "
                f"{min_err:.0f}% forecast error. No event below this "
                f"threshold has ever resulted in controlled outages."
            )

    # Insight: supply-side vs demand-side
    supply = [
        p for p in periods
        if p.get("cause_classification") == "supply_side"
    ]
    supply_fail = sum(
        1 for p in supply
        if p.get("outcome") in ("catastrophic", "near_miss")
    )
    demand = [
        p for p in periods
        if p.get("cause_classification") == "demand_side"
    ]
    demand_fail = sum(
        1 for p in demand
        if p.get("outcome") in ("catastrophic", "near_miss")
    )
    if supply and demand:
        supply_rate = supply_fail / len(supply) * 100 if supply else 0
        demand_rate = demand_fail / len(demand) * 100 if demand else 0
        if supply_rate > demand_rate:
            statements.append(
                f"Supply-side events fail at {supply_rate:.0f}% vs "
                f"{demand_rate:.0f}% for demand-side. Generator failures "
                f"are rarer but far more likely to cascade into catastrophe."
            )

    # Insight: planned outages as predictor
    with_high_planned = [
        p for p in periods
        if (p.get("pre_period_planned_outage_mw") or 0) > 8000
    ]
    high_planned_fail = sum(
        1 for p in with_high_planned
        if p.get("outcome") in ("catastrophic", "near_miss")
    )
    if with_high_planned:
        rate = high_planned_fail / len(with_high_planned) * 100
        statements.append(
            f"Periods with >8,000 MW planned outages going in had a "
            f"{rate:.0f}% failure rate — high maintenance backlog is a "
            f"leading indicator of grid vulnerability."
        )

    # Insight: winter vs summer
    winter = [p for p in periods if p.get("season") == "winter"]
    winter_cat = sum(
        1 for p in winter if p.get("outcome") == "catastrophic"
    )
    summer = [p for p in periods if p.get("season") == "summer"]
    summer_cat = sum(
        1 for p in summer if p.get("outcome") == "catastrophic"
    )
    if winter and summer:
        statements.append(
            f"Winter accounts for {winter_cat} of {len(catastrophic)} "
            f"catastrophic events despite fewer total periods — "
            f"winter stress is lower-probability but higher-consequence."
        )

    # Insight: post-Uri improvement
    post_uri = [
        p for p in periods
        if (p.get("year") or 0) >= 2022
        and p.get("outcome") in ("managed", "normal")
    ]
    if post_uri:
        statements.append(
            f"Since post-Uri reforms (2022+), {len(post_uri)} of "
            f"{len([p for p in periods if (p.get('year') or 0) >= 2022])} "
            f"periods resolved safely — early evidence that winterization "
            f"and market reforms are improving grid resilience."
        )

    return statements


def _build_fingerprint_narratives(hist: dict) -> list[dict]:
    """
    Enrich notable events with full fingerprint narratives.

    Args:
        hist: The historical analysis dict from _analyze_historical.

    Returns:
        List of enriched event dicts with narrative content.
    """
    notable = hist.get("notable_events", [])
    enriched = []

    for event in notable:
        notes = event.get("notes", "")
        # Try to find matching fingerprint by notes or year
        fp_match = _find_fingerprint_for_event(event)
        enriched.append({
            **event,
            "fingerprint_notes": fp_match.get("notes") if fp_match else notes,
            "fingerprint_label": fp_match.get("label") if fp_match else None,
            "load_shed_mw": fp_match.get("load_shed_mw") if fp_match else None,
            "customers_affected": (
                fp_match.get("customers_affected") if fp_match else None
            ),
            "eea_level_reached": (
                fp_match.get("eea_level_reached") if fp_match else None
            ),
        })

    return enriched


def _find_fingerprint_for_event(event: dict) -> dict | None:
    """Match a notable event to its HISTORICAL_FINGERPRINTS entry."""
    year = event.get("year")
    season = event.get("season")

    year_season_map = {
        (2021, "winter"): "uri_feb_2021",
        (2011, "winter"): "groundhog_day_2011",
        (2022, "winter"): "elliott_dec_2022",
        (2006, "spring"): "spring_apr_2006",
        (2023, "summer"): "summer_aug_sep_2023",
        (2024, "winter"): "winter_heather_jan_2024",
        (2024, "summer"): "summer_aug_2024",
        (2025, "summer"): "summer_2025",
        (2026, "winter"): "winter_fern_jan_2026",
    }

    key = year_season_map.get((year, season))
    if key:
        return HISTORICAL_FINGERPRINTS.get(key)
    return None
