"""Feature engineering for hourly ERCOT load archive + weather data."""

import math
import logging
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# US federal holidays (approximate — covers major ones)
_US_HOLIDAYS_MMDD = {
    "01-01", "01-20", "02-17", "05-26", "06-19",
    "07-04", "09-01", "10-13", "11-11", "11-27", "12-25",
}

# Zone columns expected in ERCOT load data (may vary by year)
_ZONE_PREFIXES = [
    "coast", "east", "far_west", "north", "north_central",
    "south_central", "southern", "west",
]


def build_feature_matrix(load_df: pd.DataFrame,
                         weather_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the full feature matrix from raw load and weather data.

    Combines ERCOT hourly load with weather, adds cyclical time encoding,
    lagged features, rolling statistics, zone ratios, deltas, calendar
    features, targets, and stress labels.

    Args:
        load_df: ERCOT hourly load with interval_start and zone columns.
        weather_df: Hourly weather with time, temperature_f, humidity_pct,
                    wind_speed_mph.

    Returns:
        DataFrame with ~35 feature columns per row, NaN-free in valid range.
    """
    df = _prepare_base(load_df)
    df = _merge_weather(df, weather_df)
    df = _add_cyclical_time(df)
    df = _add_zone_ratios(df)
    df = _add_lagged_load(df)
    df = _add_rolling_stats(df)
    df = _add_deltas(df)
    df = _add_calendar(df)
    df = _add_targets(df)
    df = _add_stress_labels(df)
    df = _drop_warmup_rows(df)

    logger.info("Feature matrix: %d rows x %d columns", len(df), len(df.columns))
    return df


def _prepare_base(load_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract the total ERCOT load and zone columns into a clean DataFrame.

    Args:
        load_df: Raw load data from gridstatus.

    Returns:
        DataFrame with interval_start, ercot_mw, and zone MW columns.
    """
    df = load_df.copy()
    df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
    df = df.sort_values("interval_start").reset_index(drop=True)

    # Find the total load column
    total_col = _find_total_column(df)
    df["ercot_mw"] = df[total_col].astype(float)

    # Extract zone columns
    zone_cols = _find_zone_columns(df)
    for zone_name, col_name in zone_cols.items():
        df[f"zone_{zone_name}_mw"] = df[col_name].astype(float)

    keep = ["interval_start", "ercot_mw"]
    keep += [c for c in df.columns if c.startswith("zone_")]
    return df[keep].copy()


def _find_total_column(df: pd.DataFrame) -> str:
    """
    Find the column representing total ERCOT system load.

    Args:
        df: Load DataFrame.

    Returns:
        Column name for total load.
    """
    candidates = ["ercot", "system_total", "total"]
    for candidate in candidates:
        for col in df.columns:
            if candidate in col.lower() and "zone" not in col.lower():
                return col

    # Fallback: first numeric column after timestamp
    for col in df.columns:
        if col != "interval_start" and df[col].dtype in [float, int, np.float64]:
            return col

    raise ValueError("Could not find total load column in ERCOT data")


def _find_zone_columns(df: pd.DataFrame) -> dict:
    """
    Map zone prefixes to actual column names in the DataFrame.

    Args:
        df: Load DataFrame.

    Returns:
        Dict mapping zone_name -> column_name.
    """
    found = {}
    for prefix in _ZONE_PREFIXES:
        for col in df.columns:
            col_lower = col.lower()
            if prefix in col_lower and col_lower != "interval_start":
                found[prefix] = col
                break
    return found


def _merge_weather(df: pd.DataFrame,
                   weather_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge weather data onto load data by nearest hour.

    Args:
        df: Load DataFrame with interval_start.
        weather_df: Weather DataFrame with time column.

    Returns:
        DataFrame with temperature_f, humidity_pct, wind_speed_mph added.
    """
    weather = weather_df.copy()
    weather["time"] = pd.to_datetime(weather["time"], utc=True)
    weather = weather.rename(columns={"time": "interval_start"})
    weather = weather.set_index("interval_start").sort_index()

    df = df.set_index("interval_start").sort_index()
    df = df.join(weather, how="left")

    # Forward-fill gaps (max 3 hours)
    for col in ["temperature_f", "humidity_pct", "wind_speed_mph"]:
        if col in df.columns:
            df[col] = df[col].ffill(limit=3)
            df[col] = df[col].fillna(df[col].median())

    df = df.reset_index()
    return df


def _add_cyclical_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add sine/cosine encoding for hour, day-of-week, and month.

    Args:
        df: DataFrame with interval_start.

    Returns:
        DataFrame with 6 cyclical columns added.
    """
    dt = df["interval_start"]
    hour = dt.dt.hour + dt.dt.minute / 60.0
    dow = dt.dt.dayofweek
    month = dt.dt.month

    df["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    df["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    df["month_cos"] = np.cos(2 * np.pi * month / 12.0)

    return df


def _add_zone_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add each zone's load as a fraction of total ERCOT load.

    Args:
        df: DataFrame with ercot_mw and zone_*_mw columns.

    Returns:
        DataFrame with zone_*_ratio columns added.
    """
    zone_cols = [c for c in df.columns if c.startswith("zone_") and c.endswith("_mw")]
    for col in zone_cols:
        ratio_name = col.replace("_mw", "_ratio")
        df[ratio_name] = df[col] / df["ercot_mw"].clip(lower=1.0)
    return df


def _add_lagged_load(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add lagged total load features: t-1h, t-2h, t-4h, t-12h, t-24h, t-168h.

    Args:
        df: DataFrame with ercot_mw.

    Returns:
        DataFrame with lag columns added.
    """
    lags = {"lag_1h": 1, "lag_2h": 2, "lag_4h": 4,
            "lag_12h": 12, "lag_24h": 24, "lag_168h": 168}
    for name, offset in lags.items():
        df[name] = df["ercot_mw"].shift(offset)
    return df


def _add_rolling_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add rolling mean and standard deviation of load.

    Windows: 4h, 24h, 24h std.

    Args:
        df: DataFrame with ercot_mw.

    Returns:
        DataFrame with rolling stat columns added.
    """
    df["rolling_4h_mean"] = df["ercot_mw"].rolling(4, min_periods=1).mean()
    df["rolling_24h_mean"] = df["ercot_mw"].rolling(24, min_periods=1).mean()
    df["rolling_24h_std"] = df["ercot_mw"].rolling(24, min_periods=2).std()
    df["rolling_24h_std"] = df["rolling_24h_std"].fillna(0.0)
    return df


def _add_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add load change features: delta from t-1h, t-4h, t-24h.

    Args:
        df: DataFrame with ercot_mw.

    Returns:
        DataFrame with delta columns added.
    """
    df["delta_1h"] = df["ercot_mw"] - df["ercot_mw"].shift(1)
    df["delta_4h"] = df["ercot_mw"] - df["ercot_mw"].shift(4)
    df["delta_24h"] = df["ercot_mw"] - df["ercot_mw"].shift(24)
    return df


def _add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add calendar features: is_weekend, is_holiday.

    Args:
        df: DataFrame with interval_start.

    Returns:
        DataFrame with binary calendar columns.
    """
    dt = df["interval_start"]
    df["is_weekend"] = (dt.dt.dayofweek >= 5).astype(float)
    mmdd = dt.dt.strftime("%m-%d")
    df["is_holiday"] = mmdd.isin(_US_HOLIDAYS_MMDD).astype(float)
    return df


def _add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add prediction targets: actual load at t+1h, t+4h, t+12h.

    Args:
        df: DataFrame with ercot_mw.

    Returns:
        DataFrame with target columns (NaN at end where shift overflows).
    """
    df["target_1h"] = df["ercot_mw"].shift(-1)
    df["target_4h"] = df["ercot_mw"].shift(-4)
    df["target_12h"] = df["ercot_mw"].shift(-12)
    return df


def _add_stress_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add binary stress label: 1 when load exceeds 30-day rolling max by >5%
    AND hourly ramp exceeds 2000 MW.

    Args:
        df: DataFrame with ercot_mw.

    Returns:
        DataFrame with is_stress column.
    """
    rolling_max = df["ercot_mw"].rolling(720, min_periods=24).max()
    exceeds_max = df["ercot_mw"] > (rolling_max.shift(1) * 1.05)
    ramp = df["ercot_mw"].diff().abs()
    high_ramp = ramp > 2000

    df["is_stress"] = (exceeds_max & high_ramp).astype(float)
    return df


def _drop_warmup_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows where lagged features or targets are NaN.

    Removes the first 168 rows (1 week of lags) and last 12 rows (target shift).

    Args:
        df: Feature DataFrame.

    Returns:
        Trimmed DataFrame with no NaN in feature/target columns.
    """
    # Drop first 168 rows (lag_168h needs 168 hours of history)
    df = df.iloc[168:].copy()

    # Drop last 12 rows (target_12h shifts forward 12)
    df = df.iloc[:-12].copy()

    # Fill any remaining NaN in weather columns
    for col in ["temperature_f", "humidity_pct", "wind_speed_mph"]:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    df = df.reset_index(drop=True)
    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """
    Return the list of feature column names (excludes targets, timestamp, stress label).

    Args:
        df: Feature DataFrame.

    Returns:
        List of column names to use as model input.
    """
    exclude = {"interval_start", "target_1h", "target_4h", "target_12h", "is_stress"}
    return [c for c in df.columns if c not in exclude]


def get_target_columns() -> list[str]:
    """Return the target column names."""
    return ["target_1h", "target_4h", "target_12h"]
