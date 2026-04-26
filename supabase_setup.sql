-- ============================================================================
-- ERCOT Grid Stress Analyzer — Supabase Table Setup
-- Run each section in the Supabase SQL Editor (supabase.com > your project > SQL Editor)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Table 1: stress_events
-- Automatic post-mortem log of every detected stress event.
-- ----------------------------------------------------------------------------

CREATE TABLE stress_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    cause TEXT NOT NULL,
    peak_error_mw FLOAT NOT NULL,
    peak_error_pct FLOAT NOT NULL,
    error_growth_rate_mw_per_hour FLOAT NOT NULL,
    response_lag_minutes INTEGER,
    response_adequate BOOLEAN,
    fingerprint_match TEXT,
    fingerprint_similarity FLOAT,
    plain_summary TEXT,
    raw_snapshot JSONB
);


-- ----------------------------------------------------------------------------
-- Table 2: historical_periods
-- One row per labeled peak period (summer or winter) going back to 2003.
-- Populated by the one-time historical ingestion job on first deploy.
-- ----------------------------------------------------------------------------

CREATE TABLE historical_periods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    season TEXT NOT NULL,
    year INTEGER NOT NULL,
    peak_actual_mw FLOAT,
    peak_forecast_mw FLOAT,
    peak_error_mw FLOAT,
    peak_error_pct FLOAT,
    max_thermal_outage_mw FLOAT,
    min_reserve_margin_pct FLOAT,
    pre_period_planned_outage_mw FLOAT,
    cause_classification TEXT,
    response_lag_minutes INTEGER,
    outcome TEXT NOT NULL,
    outcome_source TEXT,
    notes TEXT
);


-- ----------------------------------------------------------------------------
-- Table 3: grid_snapshots
-- Append-only 5-minute snapshots for trend analysis.
-- ----------------------------------------------------------------------------

CREATE TABLE grid_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    forecast_mw FLOAT NOT NULL,
    actual_mw FLOAT NOT NULL,
    error_mw FLOAT NOT NULL,
    error_pct FLOAT NOT NULL,
    reserve_margin_mw FLOAT,
    physical_responsive_capability_mw FLOAT,
    thermal_outage_mw FLOAT,
    reserve_price_adder FLOAT,
    weather_temp_f FLOAT,
    stress_score FLOAT
);
