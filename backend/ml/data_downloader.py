"""Download ERCOT hourly load archive + Open-Meteo weather. Cache as parquet."""

import logging
import ssl
from pathlib import Path

import httpx
import pandas as pd

from backend.exceptions import ERCOTFetchError, WeatherFetchError

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"

# Dallas, TX — proxy for ERCOT load center
_DALLAS_LAT = 32.78
_DALLAS_LON = -96.80
_OPEN_METEO_HISTORICAL = "https://archive-api.open-meteo.com/v1/archive"

# Years to download
DEFAULT_START_YEAR = 2021
DEFAULT_END_YEAR = 2025


def ensure_cache_dir():
    """Create cache directory if it does not exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def download_ercot_load(start_year: int = DEFAULT_START_YEAR,
                        end_year: int = DEFAULT_END_YEAR) -> pd.DataFrame:
    """
    Download ERCOT hourly load archive via gridstatus.

    Caches each year as a separate parquet file. Skips years already cached.
    Returns concatenated DataFrame for the full range.

    Args:
        start_year: First year to download.
        end_year: Last year to download (inclusive).

    Returns:
        DataFrame with hourly load data, all years concatenated.
    """
    ensure_cache_dir()
    # Disable SSL for ERCOT MIS
    ssl._create_default_https_context = ssl._create_unverified_context

    frames = []
    for year in range(start_year, end_year + 1):
        parquet_path = CACHE_DIR / f"ercot_load_{year}.parquet"

        if parquet_path.exists():
            logger.info("Loading cached ERCOT load for %d", year)
            df = pd.read_parquet(parquet_path)
            frames.append(df)
            continue

        logger.info("Downloading ERCOT load for %d...", year)
        df = _fetch_ercot_year(year)
        df.to_parquet(parquet_path, index=False)
        logger.info("Cached %d rows for %d", len(df), year)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("interval_start").reset_index(drop=True)
    return combined


def _fetch_ercot_year(year: int) -> pd.DataFrame:
    """
    Fetch one year of ERCOT hourly load from gridstatus.

    Args:
        year: Calendar year to fetch.

    Returns:
        DataFrame with standardized column names.
    """
    try:
        import gridstatus
        ercot = gridstatus.Ercot()
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        df = ercot.get_hourly_load_post_settlements(start=start, end=end)
    except Exception as exc:
        raise ERCOTFetchError(
            f"Failed to download ERCOT load for {year}: {exc}"
        ) from exc

    if df is None or df.empty:
        raise ERCOTFetchError(f"No ERCOT load data returned for {year}")

    return _standardize_load_columns(df)


def _standardize_load_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize column names from gridstatus to a consistent schema.

    Args:
        df: Raw gridstatus load DataFrame.

    Returns:
        DataFrame with lowercase snake_case columns.
    """
    rename_map = {}
    for col in df.columns:
        lower = col.lower().replace(" ", "_").replace("-", "_")
        rename_map[col] = lower

    df = df.rename(columns=rename_map)

    # Ensure interval_start exists
    time_candidates = ["interval_start", "time", "timestamp", "datetime"]
    for candidate in time_candidates:
        if candidate in df.columns:
            df = df.rename(columns={candidate: "interval_start"})
            break

    if "interval_start" not in df.columns:
        raise ERCOTFetchError("Could not find timestamp column in load data")

    df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
    return df


def download_weather(start_year: int = DEFAULT_START_YEAR,
                     end_year: int = DEFAULT_END_YEAR) -> pd.DataFrame:
    """
    Download hourly historical weather from Open-Meteo for Dallas.

    Caches as a single parquet file for the full range.

    Args:
        start_year: First year.
        end_year: Last year (inclusive).

    Returns:
        DataFrame with hourly temperature, humidity, wind speed.
    """
    ensure_cache_dir()
    parquet_path = CACHE_DIR / f"weather_{start_year}_{end_year}.parquet"

    if parquet_path.exists():
        logger.info("Loading cached weather data")
        return pd.read_parquet(parquet_path)

    logger.info("Downloading weather data %d-%d...", start_year, end_year)
    df = _fetch_weather_range(start_year, end_year)
    df.to_parquet(parquet_path, index=False)
    logger.info("Cached %d weather rows", len(df))
    return df


def _fetch_weather_range(start_year: int, end_year: int) -> pd.DataFrame:
    """
    Fetch historical hourly weather from Open-Meteo archive API.

    Args:
        start_year: First year.
        end_year: Last year.

    Returns:
        DataFrame with time, temperature_f, humidity, wind_speed_mph.
    """
    start_date = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"

    try:
        resp = httpx.get(
            _OPEN_METEO_HISTORICAL,
            params={
                "latitude": _DALLAS_LAT,
                "longitude": _DALLAS_LON,
                "start_date": start_date,
                "end_date": end_date,
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise WeatherFetchError(
            f"Failed to download weather data: {exc}"
        ) from exc

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    humidity = hourly.get("relative_humidity_2m", [])
    wind = hourly.get("wind_speed_10m", [])

    df = pd.DataFrame({
        "time": pd.to_datetime(times, utc=True),
        "temperature_f": temps,
        "humidity_pct": humidity,
        "wind_speed_mph": wind,
    })

    return df


def load_cached_data(start_year: int = DEFAULT_START_YEAR,
                     end_year: int = DEFAULT_END_YEAR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load previously cached ERCOT load and weather data.

    Args:
        start_year: First year.
        end_year: Last year.

    Returns:
        Tuple of (load_df, weather_df).
    """
    load_frames = []
    for year in range(start_year, end_year + 1):
        path = CACHE_DIR / f"ercot_load_{year}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No cached load data for {year}")
        load_frames.append(pd.read_parquet(path))

    load_df = pd.concat(load_frames, ignore_index=True)
    load_df = load_df.sort_values("interval_start").reset_index(drop=True)

    weather_path = CACHE_DIR / f"weather_{start_year}_{end_year}.parquet"
    if not weather_path.exists():
        raise FileNotFoundError("No cached weather data")
    weather_df = pd.read_parquet(weather_path)

    return load_df, weather_df


def is_data_cached(start_year: int = DEFAULT_START_YEAR,
                   end_year: int = DEFAULT_END_YEAR) -> bool:
    """
    Check whether all required cache files exist.

    Args:
        start_year: First year.
        end_year: Last year.

    Returns:
        True if all years + weather are cached.
    """
    for year in range(start_year, end_year + 1):
        if not (CACHE_DIR / f"ercot_load_{year}.parquet").exists():
            return False
    if not (CACHE_DIR / f"weather_{start_year}_{end_year}.parquet").exists():
        return False
    return True
