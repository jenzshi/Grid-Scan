"""ERCOT data fetching via gridstatus. Mock mode returns realistic stressed data."""

import ssl
import random
import logging
from datetime import datetime, timezone, timedelta

from backend.config import MOCK_MODE
from backend.exceptions import ERCOTFetchError

logger = logging.getLogger(__name__)

# Disable SSL verification for ERCOT MIS downloads
ssl._create_default_https_context = ssl._create_unverified_context


def _get_ercot():
    """Create a gridstatus ERCOT client."""
    import gridstatus
    return gridstatus.Ercot()


def get_current_load() -> dict:
    """Fetch real-time load forecast vs actual from gridstatus."""
    if MOCK_MODE:
        return _mock_current_load()
    try:
        return _live_current_load()
    except Exception as exc:
        raise ERCOTFetchError(f"Failed to fetch current load: {exc}") from exc


def get_reserve_status() -> dict:
    """Fetch PRC, operating reserves, ORDC adder."""
    if MOCK_MODE:
        return _mock_reserve_status()
    try:
        return _live_reserve_status()
    except Exception as exc:
        raise ERCOTFetchError(f"Failed to fetch reserve status: {exc}") from exc


def get_thermal_outages() -> dict:
    """Fetch current thermal outage capacity in MW."""
    if MOCK_MODE:
        return _mock_thermal_outages()
    try:
        return _live_thermal_outages()
    except Exception as exc:
        raise ERCOTFetchError(f"Failed to fetch thermal outages: {exc}") from exc


def get_wind_status() -> dict:
    """
    Fetch current wind generation vs forecast.

    Returns:
        Dict with wind_actual_mw, wind_forecast_mw, wind_shortfall_mw.
    """
    if MOCK_MODE:
        return _mock_wind_status()
    try:
        return _live_wind_status()
    except Exception as exc:
        raise ERCOTFetchError(f"Failed to fetch wind status: {exc}") from exc


def get_solar_status() -> dict:
    """
    Fetch current solar generation vs forecast.

    Returns:
        Dict with solar_actual_mw, solar_forecast_mw, solar_shortfall_mw.
    """
    if MOCK_MODE:
        return _mock_solar_status()
    try:
        return _live_solar_status()
    except Exception as exc:
        raise ERCOTFetchError(f"Failed to fetch solar status: {exc}") from exc


def get_fuel_mix() -> dict:
    """
    Fetch current generation by fuel type.

    Returns:
        Dict with gas_mw, coal_mw, nuclear_mw, wind_mw, solar_mw,
        storage_mw, other_mw.
    """
    if MOCK_MODE:
        return _mock_fuel_mix()
    try:
        return _live_fuel_mix()
    except Exception as exc:
        raise ERCOTFetchError(f"Failed to fetch fuel mix: {exc}") from exc


def get_operations_messages(hours_back: int = 24) -> list[dict]:
    """Fetch ERCOT operational messages for response tracking."""
    if MOCK_MODE:
        return _mock_operations_messages(hours_back)
    try:
        return _live_operations_messages(hours_back)
    except Exception as exc:
        raise ERCOTFetchError(
            f"Failed to fetch operations messages: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Live implementations via gridstatus
# ---------------------------------------------------------------------------

def _live_current_load() -> dict:
    """
    Fetch real-time actual demand from get_real_time_system_conditions
    and current-hour forecast from get_load_forecast.
    """
    ercot = _get_ercot()

    # Actual demand from real-time system conditions
    rtsc = ercot.get_real_time_system_conditions(date="latest")
    if rtsc is None or rtsc.empty:
        raise ERCOTFetchError("No real-time system conditions data")

    actual_mw = float(rtsc["Actual System Demand"].iloc[-1])

    # Forecast from load forecast — find closest hour to now
    forecast_mw = actual_mw  # fallback
    try:
        lf = ercot.get_load_forecast(date="latest")
        if lf is not None and not lf.empty:
            now = datetime.now(timezone.utc)
            lf_times = lf["Interval Start"]
            # Find the row closest to current time
            diffs = abs(lf_times - now)
            closest_idx = diffs.idxmin()
            forecast_mw = float(lf.loc[closest_idx, "System Total"])
    except Exception:
        logger.warning("Could not fetch load forecast, using actual as fallback")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "forecast_mw": round(forecast_mw, 1),
        "actual_mw": round(actual_mw, 1),
    }


def _live_reserve_status() -> dict:
    """
    Derive reserve data from real-time system conditions.
    Total capacity minus actual demand = reserve margin.
    """
    ercot = _get_ercot()

    rtsc = ercot.get_real_time_system_conditions(date="latest")
    if rtsc is None or rtsc.empty:
        raise ERCOTFetchError("No real-time system conditions data")

    row = rtsc.iloc[-1]
    actual = float(row["Actual System Demand"])
    capacity = float(row["Total System Capacity excluding Ancillary Services"])
    reserve_mw = capacity - actual

    # PRC is not directly available — estimate from reserves
    # Conservative: PRC is typically 60-80% of total reserves
    prc_mw = reserve_mw * 0.7

    # Try to get ORDC adder
    adder = 0.0
    try:
        spp = ercot.get_spp(date="latest")
        if spp is not None and not spp.empty:
            adder_col = _find_column(spp, ["ORDC", "Adder"])
            if adder_col:
                adder = float(spp[adder_col].iloc[-1])
    except Exception:
        pass

    return {
        "physical_responsive_capability_mw": round(prc_mw, 1),
        "reserve_margin_mw": round(max(reserve_mw, 0), 1),
        "reserve_price_adder": round(adder, 2),
    }


def _live_thermal_outages() -> dict:
    """Fetch current thermal outage capacity from hourly resource outages."""
    ercot = _get_ercot()

    try:
        df = ercot.get_hourly_resource_outage_capacity(date="latest")
        if df is not None and not df.empty:
            # Get the earliest forecast row (closest to now)
            outage_mw = float(df["Total Resource MW"].iloc[0])
            return {"thermal_outage_mw": round(outage_mw, 1)}
    except Exception:
        logger.warning("Could not fetch outage data from hourly report")

    # Fallback: derive from system conditions
    try:
        rtsc = ercot.get_real_time_system_conditions(date="latest")
        if rtsc is not None and not rtsc.empty:
            row = rtsc.iloc[-1]
            capacity = float(
                row["Total System Capacity excluding Ancillary Services"]
            )
            # Typical ERCOT installed capacity ~90-100 GW
            # Outage = installed - available, rough estimate
            installed_estimate = 95000.0
            outage_estimate = installed_estimate - capacity
            return {"thermal_outage_mw": round(max(outage_estimate, 0), 1)}
    except Exception:
        pass

    return {"thermal_outage_mw": 0.0}


def _live_operations_messages(hours_back: int) -> list[dict]:
    """Fetch ERCOT operational messages."""
    ercot = _get_ercot()

    try:
        msgs = ercot.get_operations_messages(date="latest")
        if msgs is None or msgs.empty:
            return []

        results = []
        for _, row in msgs.iterrows():
            timestamp = row.get("Time") or row.get("Timestamp")
            message = str(row.get("Message", "") or row.get("Notice", "") or "")
            msg_lower = message.lower()

            msg_type = "informational"
            if "conservation" in msg_lower:
                msg_type = "conservation_appeal"
            elif "eea" in msg_lower or "emergency" in msg_lower:
                if "eea3" in msg_lower or "level 3" in msg_lower:
                    msg_type = "eea3"
                elif "eea2" in msg_lower or "level 2" in msg_lower:
                    msg_type = "eea2"
                else:
                    msg_type = "eea1"

            results.append({
                "timestamp": str(timestamp),
                "type": msg_type,
                "message": message,
            })

        return results
    except Exception:
        logger.warning("Could not fetch operations messages")
        return []


def _find_column(df, candidates: list[str]) -> str | None:
    """
    Find the first matching column name from a list of candidates.

    Args:
        df: DataFrame to search columns in.
        candidates: List of possible column name substrings.

    Returns:
        Matching column name or None.
    """
    for candidate in candidates:
        for col in df.columns:
            if candidate.lower() in col.lower():
                return col
    return None


# ---------------------------------------------------------------------------
# Live implementations — wind, solar, fuel mix
# ---------------------------------------------------------------------------

def _live_wind_status() -> dict:
    """Fetch wind actual vs forecast from gridstatus."""
    ercot = _get_ercot()

    rtsc = ercot.get_real_time_system_conditions(date="latest")
    if rtsc is None or rtsc.empty:
        raise ERCOTFetchError("No real-time system conditions data for wind")

    row = rtsc.iloc[-1]
    actual = float(row.get("Current Wind Output", 0))
    forecast = actual  # fallback

    try:
        wf = ercot.get_wind_forecast(date="latest")
        if wf is not None and not wf.empty:
            now = datetime.now(timezone.utc)
            diffs = abs(wf["Interval Start"] - now)
            closest = diffs.idxmin()
            forecast = float(wf.loc[closest, "System Total"])
    except Exception:
        logger.warning("Could not fetch wind forecast, using actual as fallback")

    shortfall = max(forecast - actual, 0)
    return {
        "wind_actual_mw": round(actual, 1),
        "wind_forecast_mw": round(forecast, 1),
        "wind_shortfall_mw": round(shortfall, 1),
    }


def _live_solar_status() -> dict:
    """Fetch solar actual vs forecast from gridstatus."""
    ercot = _get_ercot()

    rtsc = ercot.get_real_time_system_conditions(date="latest")
    if rtsc is None or rtsc.empty:
        raise ERCOTFetchError("No real-time system conditions data for solar")

    row = rtsc.iloc[-1]
    actual = float(row.get("Current Solar Output", 0))
    forecast = actual

    try:
        sf = ercot.get_solar_forecast(date="latest")
        if sf is not None and not sf.empty:
            now = datetime.now(timezone.utc)
            diffs = abs(sf["Interval Start"] - now)
            closest = diffs.idxmin()
            forecast = float(sf.loc[closest, "System Total"])
    except Exception:
        logger.warning("Could not fetch solar forecast, using actual as fallback")

    shortfall = max(forecast - actual, 0)
    return {
        "solar_actual_mw": round(actual, 1),
        "solar_forecast_mw": round(forecast, 1),
        "solar_shortfall_mw": round(shortfall, 1),
    }


def _live_fuel_mix() -> dict:
    """Fetch current generation by fuel type from gridstatus."""
    ercot = _get_ercot()

    try:
        fm = ercot.get_fuel_mix(date="latest")
        if fm is not None and not fm.empty:
            row = fm.iloc[-1]
            return _extract_fuel_mix(row)
    except Exception:
        logger.warning("Could not fetch fuel mix from get_fuel_mix")

    return _default_fuel_mix()


def _extract_fuel_mix(row) -> dict:
    """
    Extract fuel mix MW values from a gridstatus fuel mix row.

    Args:
        row: A pandas Series from the fuel mix DataFrame.

    Returns:
        Dict with gas_mw, coal_mw, nuclear_mw, wind_mw, solar_mw,
        storage_mw, other_mw.
    """
    def _get(col_substr):
        for col in row.index:
            if col_substr.lower() in col.lower():
                return float(row[col])
        return 0.0

    gas = _get("Gas")
    coal = _get("Coal")
    nuclear = _get("Nuclear")
    wind = _get("Wind")
    solar = _get("Solar")
    storage = _get("Storage") + _get("Battery")
    total = sum([gas, coal, nuclear, wind, solar, storage])
    other = max(float(row.get("Total", total)) - total, 0.0)

    return {
        "gas_mw": round(gas, 1),
        "coal_mw": round(coal, 1),
        "nuclear_mw": round(nuclear, 1),
        "wind_mw": round(wind, 1),
        "solar_mw": round(solar, 1),
        "storage_mw": round(storage, 1),
        "other_mw": round(other, 1),
    }


def _default_fuel_mix() -> dict:
    """Return zeroed fuel mix when data is unavailable."""
    return {
        "gas_mw": 0.0,
        "coal_mw": 0.0,
        "nuclear_mw": 0.0,
        "wind_mw": 0.0,
        "solar_mw": 0.0,
        "storage_mw": 0.0,
        "other_mw": 0.0,
    }


# ---------------------------------------------------------------------------
# Mock implementations — realistic stressed-afternoon scenario
# ---------------------------------------------------------------------------

def _mock_current_load() -> dict:
    """Simulate a hot summer afternoon with demand exceeding forecast."""
    base_forecast = 72000.0
    noise = random.uniform(-500, 500)
    forecast_mw = base_forecast + noise
    overshoot = random.uniform(0.03, 0.07)
    actual_mw = forecast_mw * (1 + overshoot)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "forecast_mw": round(forecast_mw, 1),
        "actual_mw": round(actual_mw, 1),
    }


def _mock_reserve_status() -> dict:
    """Simulate moderately stressed reserves."""
    return {
        "physical_responsive_capability_mw": round(random.uniform(4500, 6500), 1),
        "reserve_margin_mw": round(random.uniform(5000, 8000), 1),
        "reserve_price_adder": round(random.uniform(5.0, 50.0), 2),
    }


def _mock_thermal_outages() -> dict:
    """Simulate typical summer thermal outages."""
    return {"thermal_outage_mw": round(random.uniform(2500, 5000), 1)}


def _mock_wind_status() -> dict:
    """Simulate wind underperforming forecast — typical afternoon shortfall."""
    forecast = round(random.uniform(16000, 20000), 1)
    actual = round(forecast * random.uniform(0.60, 0.80), 1)
    shortfall = round(forecast - actual, 1)
    return {
        "wind_actual_mw": actual,
        "wind_forecast_mw": forecast,
        "wind_shortfall_mw": shortfall,
    }


def _mock_solar_status() -> dict:
    """Simulate solar slightly below forecast — cloud cover or haze."""
    forecast = round(random.uniform(7000, 10000), 1)
    actual = round(forecast * random.uniform(0.80, 0.95), 1)
    shortfall = round(max(forecast - actual, 0), 1)
    return {
        "solar_actual_mw": actual,
        "solar_forecast_mw": forecast,
        "solar_shortfall_mw": shortfall,
    }


def _mock_fuel_mix() -> dict:
    """Simulate typical ERCOT afternoon generation mix."""
    return {
        "gas_mw": round(random.uniform(32000, 38000), 1),
        "coal_mw": round(random.uniform(6000, 9000), 1),
        "nuclear_mw": round(random.uniform(4800, 5200), 1),
        "wind_mw": round(random.uniform(12000, 16000), 1),
        "solar_mw": round(random.uniform(6000, 9000), 1),
        "storage_mw": round(random.uniform(1000, 3000), 1),
        "other_mw": round(random.uniform(500, 1500), 1),
    }


def _mock_operations_messages(hours_back: int) -> list[dict]:
    """Return a small set of mock operational messages."""
    now = datetime.now(timezone.utc)
    return [
        {
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "type": "conservation_appeal",
            "message": "ERCOT issues conservation appeal due to high demand.",
        },
        {
            "timestamp": (now - timedelta(hours=6)).isoformat(),
            "type": "informational",
            "message": "ERCOT expects tight conditions this afternoon.",
        },
    ]
