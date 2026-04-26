"""Environment variables, grid thresholds, and historical fingerprints."""

import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

GRIDS = {
    "ERCOT": {
        "error_flag_pct": 0.05,
        "growth_rate_danger_mw_per_hour": 1000,
        "prc_low_threshold_mw": 5500,
        "reserve_margin_critical_pct": 0.10,
    }
}

HISTORICAL_FINGERPRINTS = {

    # =========================================================================
    # CATASTROPHIC FAILURES — EEA3, controlled outages implemented
    # Only 4 in ERCOT history: 1989, 2006, 2011, 2021
    # =========================================================================

    "uri_feb_2021": {
        "label": "Winter Storm Uri — February 2021",
        "season": "winter",
        "cause": "supply_side",
        "seasonal_forecast_mw": 57699,
        "peak_actual_mw": 69150,
        "peak_error_mw": 11451,
        "peak_error_pct": 0.199,
        "peak_error_pct_range": (0.15, 0.45),
        "thermal_outage_mw_peak": 28000,
        "total_forced_outage_mw": 30000,
        "prc_collapsed": True,
        "eea_level_reached": 3,
        "load_shed_mw": 20000,
        "customers_affected": 4_500_000,
        "outcome": "catastrophic",
        "notes": (
            "58% of outaged units were gas-fired. Protecting 4 component types "
            "from freezing could have reduced outages 67% per FERC/NERC. "
            "11.5 GW already offline for scheduled maintenance before storm hit."
        ),
    },

    "groundhog_day_2011": {
        "label": "Groundhog Day Blizzard — February 2011",
        "season": "winter",
        "cause": "supply_side",
        "seasonal_forecast_mw": None,
        "peak_actual_mw": None,
        "peak_error_mw": None,
        "peak_error_pct_range": (0.05, 0.15),
        "thermal_outage_mw_peak": None,
        "scheduled_outage_mw_pre_storm": 11500,
        "prc_collapsed": True,
        "eea_level_reached": 3,
        "load_shed_mw": 4000,
        "customers_affected": 3_200_000,
        "outcome": "catastrophic",
        "notes": (
            "Rolling blackouts hit 75% of Texas. Same failure mode as 1989 and "
            "same recommendations issued. Neither set acted upon. "
            "Considered the direct precursor to Uri with identical systemic cause."
        ),
    },

    # =========================================================================
    # NEAR-MISSES — held but only just
    # =========================================================================

    "elliott_dec_2022": {
        "label": "Winter Storm Elliott — December 2022",
        "season": "winter",
        "cause": "demand_side",
        "seasonal_forecast_mw": 67398,
        "peak_actual_mw": 74100,
        "peak_error_mw": 6702,
        "peak_error_pct": 0.099,
        "peak_error_pct_range": (0.08, 0.12),
        "thermal_outage_mw_peak": 10000,
        "renewable_outage_mw_peak": 6000,
        "prc_min_mw": 4052,
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "near_miss",
        "notes": (
            "Four weather-related outages among 255 inspected units — massive "
            "improvement over Uri. Forecast software issue was primary failure. "
            "Response was adequate despite large error because PRC held. "
            "Shows that error magnitude alone does not predict catastrophe."
        ),
    },

    # =========================================================================
    # STRESS PATTERNS — conservation alerts, EEA1, managed events
    # =========================================================================

    "summer_aug_sep_2023": {
        "label": "Summer Evening Stress — August/September 2023",
        "season": "summer",
        "cause": "demand_side",
        "peak_actual_mw": 85464,
        "peak_error_pct_range": (0.03, 0.08),
        "prc_min_mw": 3000,
        "prc_avg_mw": 7084,
        "prc_collapsed": False,
        "eea_level_reached": 1,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "managed",
        "stress_window": "19:00-21:00 CT",
        "price_spike_count": 182,
        "notes": (
            "Demand exceeded 80,000 MW on 42 days. Solar ramp-down creates "
            "recurring evening stress distinct from midday peak. ERS deployed twice. "
            "PRC averaged 7,084 MW vs 4,830 MW in 2022 — post-Uri reforms visible."
        ),
    },

    "summer_jul_2022": {
        "label": "Record Summer Demand — July 2022",
        "season": "summer",
        "cause": "demand_side",
        "all_time_record_mw": 80148,
        "peak_error_pct_range": (0.03, 0.07),
        "prc_avg_mw": 4830,
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "managed",
        "notes": (
            "11 new peak demand records in a single summer. All-time record 80,148 MW. "
            "Grid held but PRC was significantly tighter than the following year. "
            "Useful baseline: managed high-demand with lower reserves."
        ),
    },

    "summer_may_jun_2022": {
        "label": "Deferred Maintenance Failures — May/June 2022",
        "season": "summer",
        "cause": "supply_side",
        "peak_actual_mw": 73000,
        "thermal_outage_mw_peak": 8000,
        "total_forced_outage_mw": 12000,
        "normal_june_outage_mw": 3600,
        "forced_outage_spike_mw": 2900,
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "managed",
        "notes": (
            "Critical pattern: ERCOT asked plants to delay maintenance, "
            "plants then failed under load. Rapid simultaneous supply loss "
            "is the fingerprint — 6 plants tripped within minutes. "
            "Maintenance deferral is itself a leading indicator of supply-side risk."
        ),
    },

    "summer_jun_2021": {
        "label": "Post-Uri Summer Plant Failures — June 2021",
        "season": "summer",
        "cause": "supply_side",
        "peak_actual_mw": 70000,
        "thermal_outage_mw_peak": 8000,
        "total_forced_outage_mw": 12000,
        "normal_june_outage_mw": 3600,
        "wind_shortfall_mw": 1500,
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "managed",
        "notes": (
            "Rare summer supply-side stress — typically summer is demand-driven. "
            "Uri-damaged plants still failing 4 months later. Wind also short. "
            "Combined supply squeeze with concurrent thermal and wind shortfall."
        ),
    },

    "spring_apr_2022": {
        "label": "Spring Maintenance Season Stress — April 2022",
        "season": "spring",
        "cause": "mixed",
        "peak_error_pct_range": (0.02, 0.06),
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "managed",
        "notes": (
            "Same seasonal setup as April 2006 catastrophe — high planned maintenance "
            "overlapping with unexpected demand. Managed successfully here. "
            "Spring maintenance season is a recurring structural vulnerability window."
        ),
    },

    "summer_jul_2019": {
        "label": "Low Reserve Margin Planning Stress — Summer 2019",
        "season": "summer",
        "cause": "demand_side",
        "seasonal_forecast_mw": 74853,
        "available_capacity_mw": 78929,
        "reserve_margin_pct": 0.086,
        "target_reserve_margin_pct": 0.1375,
        "worst_case_reserve_mw": 468,
        "eea_probability_pct": 0.184,
        "load_shed_probability_pct": 0.146,
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "managed",
        "notes": (
            "Lowest reserve margin in ERCOT history at the time. "
            "Multiple SARA scenarios showed negative reserves under extreme weather. "
            "Key fingerprint: reserve margin below 9% + summer peak = elevated risk "
            "even without an operational event."
        ),
    },

    # =========================================================================
    # HISTORICAL — medium/low data fidelity
    # =========================================================================

    "spring_apr_2006": {
        "label": "Spring Heat Surprise — April 2006",
        "season": "spring",
        "cause": "mixed",
        "day_ahead_forecast_mw": 49000,
        "peak_actual_mw": 53000,
        "peak_error_mw": 4000,
        "peak_error_pct": 0.082,
        "planned_outage_mw": 14500,
        "unplanned_outage_mw": 2440,
        "rapid_outage_spike_mw": 1683,
        "rapid_outage_window_minutes": 30,
        "prc_collapsed": True,
        "eea_level_reached": 3,
        "load_shed_mw": None,
        "customers_affected": None,
        "outcome": "catastrophic",
        "data_fidelity": "medium",
        "notes": (
            "The defining spring failure: mild month, high planned maintenance, "
            "unexpected temperature spike, rapid demand growth in afternoon. "
            "1,683 MW lost within 30 minutes — speed of supply loss is the key signal. "
            "PUCT found operations were correct; public communication was inadequate."
        ),
    },

    "freeze_1989": {
        "label": "December 1989 Freeze",
        "season": "winter",
        "cause": "supply_side",
        "seasonal_forecast_mw": None,
        "peak_error_mw": None,
        "peak_error_pct_range": None,
        "thermal_outage_mw_peak": None,
        "prc_collapsed": True,
        "eea_level_reached": 3,
        "outcome": "catastrophic",
        "data_fidelity": "low",
        "notes": (
            "First major winterization failure. PUCT recommendations issued and "
            "ignored. Same equipment types failed in 2011 and 2021. "
            "Use for causal pattern context only — do not use MW fields for matching."
        ),
    },

    # =========================================================================
    # 2024-2026 — POST-REFORM ERA
    # First years with full weatherization rules, battery storage at scale
    # =========================================================================

    "winter_heather_jan_2024": {
        # Sources: ERCOT Monthly January 2024, ERCOT System Operations Update
        # Feb 2024, Yes Energy analysis, ERCOT peak demand records page
        # All-time winter peak 78,349 MW set Jan 16 2024.
        # Conservation appeals issued Jan 15 (6-10am) and Jan 16 (6-9am).
        # First full winter with weatherization rules in effect including
        # wind chill parameters. Thermal forced outages ~7,000 MW — roughly
        # half of Elliott's 14,000 MW. No EEA declared. Grid held.
        "label": "Winter Storm Heather — January 2024",
        "season": "winter",
        "cause": "demand_side",
        "seasonal_forecast_mw": None,
        "peak_actual_mw": 78349,             # all-time winter record Jan 16
        "peak_error_mw": None,
        "peak_error_pct_range": (0.03, 0.07),
        "thermal_outage_mw_peak": 7000,      # vs 14,000 in Elliott, 28,000 in Uri
        "pre_storm_forced_outage_mw": 4000,  # already offline before storm hit
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "managed",
        "notes": (
            "First full winter with weatherization rules including wind chill "
            "parameters. Thermal outages ~7,000 MW — half of Elliott, quarter "
            "of Uri. Conservation appeals issued but no EEA. All-time winter "
            "peak 78,349 MW surpassed Elliott's 74,100 MW. Strong validation "
            "that post-Uri reforms are working on the generation side."
        ),
    },

    "summer_aug_2024": {
        # Sources: Utility Dive Aug 2024, ERCOT peak demand records,
        # IEEFA summer 2024 analysis, Grid Status blog Aug 20 2024,
        # ERCOT Monthly Operational Overview August 2024
        # All-time ERCOT demand record 85,559 MW set Aug 20.
        # Zero conservation appeals all summer — first time since 2019.
        # Battery discharge set new records. Solar provided ~6 GW at peak
        # despite 38.7 GW installed capacity (evening ramp-down effect).
        # Sixth-hottest summer on record.
        "label": "Record Summer Demand — August 2024",
        "season": "summer",
        "cause": "demand_side",
        "peak_actual_mw": 85559,             # all-time ERCOT record Aug 20
        "peak_error_pct_range": (0.02, 0.05),
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "normal",
        "notes": (
            "All-time ERCOT demand record 85,559 MW — surpassed 2023's "
            "85,464 MW. Zero conservation appeals issued all summer despite "
            "sixth-hottest summer on record. Battery storage and solar "
            "additions made the difference. Battery discharge peaked 20% "
            "above previous record. Strong evidence that renewable + storage "
            "buildout is materially improving summer resilience."
        ),
    },

    "summer_2025": {
        # Sources: ERCOT Summer 2025 review Sep 2025, Lone Star Solar Jan 2026,
        # Dallas Fed Jan 2025 retrospective, ERCOT Monthly May 2025
        # First time since Uri that ERCOT never asked customers to conserve.
        # Solar broke 17 generation records. Battery storage capacity nearly
        # doubled vs 2024. Coal provided only 12.5% of summer generation.
        # EEA probability dropped to 3% from 15%+ in 2024.
        "label": "Summer 2025 — Zero Conservation Appeals",
        "season": "summer",
        "cause": "demand_side",
        "peak_actual_mw": None,              # not yet in public record
        "peak_error_pct_range": (0.01, 0.04),
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 0,
        "outcome": "normal",
        "notes": (
            "Historic milestone: first time since Winter Storm Uri that ERCOT "
            "never asked customers to conserve power. Solar broke 17 generation "
            "records. Battery storage capacity nearly doubled year-over-year. "
            "EEA probability dropped to 3% from 15%+ in 2024. Solar met 15.2% "
            "of all ERCOT demand Jun-Aug. Coal dropped to 12.5%. The renewable "
            "buildout is fundamentally changing ERCOT's summer risk profile."
        ),
    },

    "winter_fern_jan_2026": {
        # Sources: ERCOT Post-Event Report Winter Storm Fern Jan 28 2026,
        # DOE Emergency Order Jan 25 2026, Texas Tribune Jan 24-29 2026,
        # Texas Policy Foundation Dec 2025 / Jan 2026 grid vulnerability report,
        # NBC News Jan 2026
        # DOE issued 202(c) emergency order authorizing backup generation.
        # 21,784 MW total outages (14,000 MW renewables, ~7,800 MW thermal).
        # No EEA declared. No rolling blackouts. Grid held.
        # But: reserve margin dropped to 10.1% (vs 17.5% in 2021).
        # Peak winter demand up 20% since Uri with roughly same dispatchable
        # capacity. Data center load growth is a structural concern.
        # ~54,300 customers lost power from localized ice/tree damage.
        "label": "Winter Storm Fern — January 2026",
        "season": "winter",
        "cause": "mixed",
        "peak_actual_mw": None,              # forecasted up to 84,000 MW
        "peak_error_pct_range": (0.03, 0.08),
        "thermal_outage_mw_peak": 7800,      # approx: 21,784 total - 14,000 renewable
        "renewable_outage_mw_peak": 14000,
        "total_outage_mw": 21784,
        "reserve_margin_pct": 0.101,         # down from 17.5% in 2021
        "prc_collapsed": False,
        "eea_level_reached": 0,
        "load_shed_mw": 0,
        "customers_affected": 54300,         # localized, ice/tree damage
        "doe_emergency_order": True,
        "outcome": "near_miss",
        "notes": (
            "DOE issued emergency order authorizing backup generation at data "
            "centers. Grid held — no EEA, no rolling blackouts. But reserve "
            "margin has dropped to 10.1% from 17.5% in 2021 despite reforms. "
            "Winter peak demand up 20% since Uri with roughly the same "
            "dispatchable generation capacity. 14,000 MW of renewable outages "
            "during the storm. 54,300 customers lost power from localized "
            "ice damage. Data center demand growth is emerging as a structural "
            "threat to winter reliability — 225 new large load requests in 2025, "
            "three-quarters from data centers."
        ),
    },
}
