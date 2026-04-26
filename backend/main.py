"""FastAPI app — route registration, CORS, static mount, polling loop."""

import asyncio
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.config import MOCK_MODE, POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)

# Polling interval: 10s in mock mode for demo, configured value otherwise
_POLL_SECONDS = 10 if MOCK_MODE else POLL_INTERVAL_SECONDS


async def poll_loop():
    """
    Background polling loop. Each tick:
    1. Fetch current ERCOT data
    2. Calculate metrics
    3. Save snapshot to storage
    4. Check if stress event should be created or resolved
    """
    from backend.data.ercot_client import (
        get_current_load,
        get_reserve_status,
        get_thermal_outages,
        get_wind_status,
        get_solar_status,
        get_fuel_mix,
    )
    from backend.data.weather_client import get_current_weather
    from backend.analysis.forecast_error import (
        calculate_error,
        calculate_growth_rate,
        is_dangerous,
    )
    from backend.analysis.classifier import classify_cause
    from backend.analysis.metrics import (
        prc_status,
        stress_score,
        reserve_headroom_pct,
    )
    from backend.analysis.event_detector import (
        detect_event,
        check_event_resolution,
        get_active_event_id,
        get_active_event_peaks,
    )
    from backend.storage.supabase_client import (
        save_snapshot,
        save_event,
        get_recent_snapshots,
    )

    while True:
        try:
            load = get_current_load()
            reserves = get_reserve_status()
            outages = get_thermal_outages()
            wind = get_wind_status()
            solar = get_solar_status()
            fuel = get_fuel_mix()
            weather = get_current_weather()

            error = calculate_error(load["forecast_mw"], load["actual_mw"])

            snapshots = get_recent_snapshots(hours=4)
            growth_rate = calculate_growth_rate(snapshots) if snapshots else 0.0

            prc_mw = reserves["physical_responsive_capability_mw"]
            score = stress_score(
                error["error_pct"],
                growth_rate,
                prc_mw,
                reserves["reserve_price_adder"],
            )

            snapshot = {
                "forecast_mw": load["forecast_mw"],
                "actual_mw": load["actual_mw"],
                "error_mw": error["error_mw"],
                "error_pct": error["error_pct"],
                "reserve_margin_mw": reserves["reserve_margin_mw"],
                "physical_responsive_capability_mw": prc_mw,
                "thermal_outage_mw": outages["thermal_outage_mw"],
                "reserve_price_adder": reserves["reserve_price_adder"],
                "weather_temp_f": weather["temp_f"],
                "stress_score": score,
                "wind_actual_mw": wind["wind_actual_mw"],
                "wind_forecast_mw": wind["wind_forecast_mw"],
                "wind_shortfall_mw": wind["wind_shortfall_mw"],
                "solar_actual_mw": solar["solar_actual_mw"],
                "solar_forecast_mw": solar["solar_forecast_mw"],
                "solar_shortfall_mw": solar["solar_shortfall_mw"],
                "gas_generation_mw": fuel.get("gas_mw", 0.0),
                "nuclear_generation_mw": fuel.get("nuclear_mw", 0.0),
                "coal_generation_mw": fuel.get("coal_mw", 0.0),
                "storage_mw": fuel.get("storage_mw", 0.0),
            }

            save_snapshot(snapshot)

            # Event detection: classify cause for the snapshot
            temp_delta = weather.get("temp_f", 0) - weather.get("forecast_temp_f", 0)
            thermal_delta = outages["thermal_outage_mw"] - 3600.0
            cause = classify_cause(
                error_mw=error["error_mw"],
                thermal_outage_delta_mw=thermal_delta,
                weather_temp_delta_f=temp_delta,
            )
            snapshot["cause"] = cause

            new_event = detect_event(snapshot, growth_rate)
            if new_event:
                save_event(new_event)

            if check_event_resolution(snapshot, growth_rate):
                logger.info("Event resolved — peaks: %s",
                            get_active_event_peaks())

        except Exception:
            logger.exception("Poll loop error")

        await asyncio.sleep(_POLL_SECONDS)


async def startup_tasks():
    """
    Run once on app startup:
    1. Check if historical archive exists in DB
    2. If not, run ingestion (generates synthetic data in mock mode)
    """
    from backend.analysis.historical_analysis import ingest_historical_archive
    try:
        ingest_historical_archive()
    except Exception:
        logger.exception("Historical archive ingestion failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background polling and historical ingestion on app startup."""
    _seed_demo_events()
    await startup_tasks()
    task = asyncio.create_task(poll_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="ERCOT Grid Stress Analyzer", lifespan=lifespan)

class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """Prevent browser caching of static assets during development."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith(('.js', '.css', '.html')) or path == '/':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

app.add_middleware(NoCacheStaticMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration
from backend.routes.live import router as live_router
from backend.routes.fingerprint import router as fingerprint_router
from backend.routes.events import router as events_router
from backend.routes.trends import router as trends_router
from backend.routes.history import router as history_router
from backend.routes.fuel_mix import router as fuel_mix_router
from backend.routes.export import router as export_router
app.include_router(live_router)
app.include_router(fingerprint_router)
app.include_router(events_router)
app.include_router(trends_router)
app.include_router(history_router)
app.include_router(fuel_mix_router)
app.include_router(export_router)


def _seed_demo_events():
    """Seed demo events so the events view has data on first load."""
    import uuid
    from datetime import datetime, timezone, timedelta
    from backend.storage.supabase_client import save_event, get_events

    try:
        existing = get_events(limit=20)
        if len(existing) >= 10:
            return
    except Exception:
        logger.exception("Could not check for existing events")
        return

    now = datetime.now(timezone.utc)
    events = [
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(hours=1)).isoformat(),
            "resolved_at": None,
            "cause": "demand_side",
            "peak_error_mw": 4100.0,
            "peak_error_pct": 0.058,
            "error_growth_rate_mw_per_hour": 900.0,
            "response_lag_minutes": None,
            "response_adequate": None,
            "fingerprint_match": None,
            "fingerprint_similarity": None,
            "plain_summary": (
                "Active event: forecast error at 4,100 MW (5.8%) and growing. "
                "Demand-side pressure from afternoon heat. No ERCOT response "
                "detected yet."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(hours=6)).isoformat(),
            "resolved_at": (now - timedelta(hours=4, minutes=30)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 3800.0,
            "peak_error_pct": 0.054,
            "error_growth_rate_mw_per_hour": 750.0,
            "response_lag_minutes": 22,
            "response_adequate": True,
            "fingerprint_match": None,
            "fingerprint_similarity": None,
            "plain_summary": (
                "Forecast error peaked at 3,800 MW (5.4%) as actual demand "
                "outpaced projections. Temperatures exceeded the forecast by "
                "6°F, pushing cooling load above expectations. Grid responded "
                "within 22 minutes with demand response deployment."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=1, hours=3)).isoformat(),
            "resolved_at": (now - timedelta(days=1, hours=1)).isoformat(),
            "cause": "supply_side",
            "peak_error_mw": 5200.0,
            "peak_error_pct": 0.073,
            "error_growth_rate_mw_per_hour": 1400.0,
            "response_lag_minutes": 45,
            "response_adequate": False,
            "fingerprint_match": "Deferred Maintenance Failures \u2014 May/June 2022",
            "fingerprint_similarity": 0.52,
            "plain_summary": (
                "Three generating units tripped offline within 20 minutes, "
                "removing 2,800 MW of capacity. The simultaneous trip pattern "
                "matches the May 2022 deferred maintenance cascade where 6 plants "
                "failed after being asked to delay scheduled maintenance. "
                "Response lag of 45 minutes was inadequate given the 1,400 MW/hour "
                "error growth rate."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=2, hours=7)).isoformat(),
            "resolved_at": (now - timedelta(days=2, hours=5)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 6100.0,
            "peak_error_pct": 0.087,
            "error_growth_rate_mw_per_hour": 1100.0,
            "response_lag_minutes": 30,
            "response_adequate": True,
            "fingerprint_match": "Winter Storm Elliott \u2014 December 2022",
            "fingerprint_similarity": 0.61,
            "plain_summary": (
                "Forecast error surged to 6,100 MW (8.7%) as actual demand "
                "significantly exceeded projections. Pattern resembles Winter Storm "
                "Elliott's forecast software error — large demand surprise with "
                "intact supply. Unlike Uri, PRC remained above 5,000 MW throughout. "
                "Conservation appeal deployed at 30 minutes was adequate."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=3, hours=5)).isoformat(),
            "resolved_at": (now - timedelta(days=3, hours=2)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 2900.0,
            "peak_error_pct": 0.041,
            "error_growth_rate_mw_per_hour": 600.0,
            "response_lag_minutes": 18,
            "response_adequate": True,
            "fingerprint_match": None,
            "fingerprint_similarity": None,
            "plain_summary": (
                "Moderate afternoon demand overshoot at 2,900 MW (4.1%). "
                "Temperature 4°F above forecast drove additional cooling load. "
                "Resolved within 3 hours as evening temperatures dropped."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=5, hours=2)).isoformat(),
            "resolved_at": (now - timedelta(days=4, hours=22)).isoformat(),
            "cause": "supply_side",
            "peak_error_mw": 7800.0,
            "peak_error_pct": 0.112,
            "error_growth_rate_mw_per_hour": 1800.0,
            "response_lag_minutes": 55,
            "response_adequate": False,
            "fingerprint_match": "Winter Storm Uri \u2014 February 2021",
            "fingerprint_similarity": 0.48,
            "plain_summary": (
                "Severe supply-side event: 7,800 MW error driven by rapid "
                "thermal generation trips. The deterioration rate of 1,800 MW/hour "
                "was dangerously fast. Pattern showed low-confidence similarity "
                "to Uri onset conditions — multiple generators failing under "
                "weather stress. Response at 55 minutes was too slow relative "
                "to the crisis speed."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=6, hours=8)).isoformat(),
            "resolved_at": (now - timedelta(days=6, hours=6)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 3200.0,
            "peak_error_pct": 0.046,
            "error_growth_rate_mw_per_hour": 500.0,
            "response_lag_minutes": 15,
            "response_adequate": True,
            "fingerprint_match": "Summer Evening Stress \u2014 August/September 2023",
            "fingerprint_similarity": 0.55,
            "plain_summary": (
                "Classic evening ramp stress: solar generation dropped while "
                "demand stayed elevated, creating a 3,200 MW gap during the "
                "19:00-21:00 CT window. This is the defining summer evening "
                "pattern seen repeatedly in 2023. Fast response at 15 minutes."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=8, hours=4)).isoformat(),
            "resolved_at": (now - timedelta(days=8, hours=1)).isoformat(),
            "cause": "supply_side",
            "peak_error_mw": 4500.0,
            "peak_error_pct": 0.064,
            "error_growth_rate_mw_per_hour": 1200.0,
            "response_lag_minutes": 38,
            "response_adequate": False,
            "fingerprint_match": "Spring Heat Surprise \u2014 April 2006",
            "fingerprint_similarity": 0.45,
            "plain_summary": (
                "Spring maintenance season vulnerability: 4,500 MW error emerged "
                "as unexpected afternoon heat coincided with high planned outages. "
                "Pattern matches April 2006 catastrophe — mild-season complacency "
                "with 12,000+ MW in planned maintenance. Rapid capacity loss of "
                "1,200 MW/hour overwhelmed the 38-minute response."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=10, hours=6)).isoformat(),
            "resolved_at": (now - timedelta(days=10, hours=4, minutes=15)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 3500.0,
            "peak_error_pct": 0.050,
            "error_growth_rate_mw_per_hour": 700.0,
            "response_lag_minutes": 20,
            "response_adequate": True,
            "fingerprint_match": None,
            "fingerprint_similarity": None,
            "plain_summary": (
                "Demand-side event driven by heat island effect in DFW metro. "
                "Forecast error at 3,500 MW (5.0%) was right at the alert "
                "threshold. Adequate response — conservation appeal issued at "
                "20 minutes, error stabilized by hour 2."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=12, hours=9)).isoformat(),
            "resolved_at": (now - timedelta(days=12, hours=6)).isoformat(),
            "cause": "supply_side",
            "peak_error_mw": 5800.0,
            "peak_error_pct": 0.083,
            "error_growth_rate_mw_per_hour": 1500.0,
            "response_lag_minutes": 42,
            "response_adequate": False,
            "fingerprint_match": "Post-Uri Summer Plant Failures \u2014 June 2021",
            "fingerprint_similarity": 0.50,
            "plain_summary": (
                "Combined thermal and wind shortfall created a 5,800 MW supply gap. "
                "Two gas plants and one wind farm underperformed simultaneously. "
                "Pattern echoes June 2021 when Uri-damaged plants were still "
                "failing months later. Response lag of 42 minutes was too slow."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=15, hours=3)).isoformat(),
            "resolved_at": (now - timedelta(days=15, hours=1, minutes=30)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 4200.0,
            "peak_error_pct": 0.060,
            "error_growth_rate_mw_per_hour": 850.0,
            "response_lag_minutes": 25,
            "response_adequate": True,
            "fingerprint_match": None,
            "fingerprint_similarity": None,
            "plain_summary": (
                "Afternoon demand spike of 4,200 MW above forecast. Driven by "
                "combination of temperature surprise and industrial load ramp. "
                "Growth rate of 850 MW/hour was concerning but response at 25 "
                "minutes kept the situation manageable."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=18, hours=5)).isoformat(),
            "resolved_at": (now - timedelta(days=18, hours=2)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 2600.0,
            "peak_error_pct": 0.037,
            "error_growth_rate_mw_per_hour": 450.0,
            "response_lag_minutes": 12,
            "response_adequate": True,
            "fingerprint_match": None,
            "fingerprint_similarity": None,
            "plain_summary": (
                "Minor demand overshoot during morning ramp. Forecast error of "
                "2,600 MW was below critical thresholds. Fast 12-minute response "
                "shows improving operational awareness."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=22, hours=7)).isoformat(),
            "resolved_at": (now - timedelta(days=22, hours=4)).isoformat(),
            "cause": "supply_side",
            "peak_error_mw": 6500.0,
            "peak_error_pct": 0.093,
            "error_growth_rate_mw_per_hour": 1600.0,
            "response_lag_minutes": 50,
            "response_adequate": False,
            "fingerprint_match": "Deferred Maintenance Failures \u2014 May/June 2022",
            "fingerprint_similarity": 0.58,
            "plain_summary": (
                "Major supply-side event: 6,500 MW error as 4 generators tripped "
                "in rapid succession. Peak error of 9.3% is in the danger zone "
                "historically associated with catastrophic outcomes. The deferred "
                "maintenance pattern — plants forced to delay service then failing "
                "under load — matched the May 2022 cascade at 58% similarity."
            ),
            "raw_snapshot": {},
        },
        {
            "id": str(uuid.uuid4()),
            "detected_at": (now - timedelta(days=28, hours=4)).isoformat(),
            "resolved_at": (now - timedelta(days=28, hours=2, minutes=45)).isoformat(),
            "cause": "demand_side",
            "peak_error_mw": 3100.0,
            "peak_error_pct": 0.044,
            "error_growth_rate_mw_per_hour": 550.0,
            "response_lag_minutes": 16,
            "response_adequate": True,
            "fingerprint_match": "Summer Evening Stress \u2014 August/September 2023",
            "fingerprint_similarity": 0.47,
            "plain_summary": (
                "Evening solar ramp-down stress. As solar output dropped 40% between "
                "18:00 and 20:00 CT, net load spiked above forecast by 3,100 MW. "
                "This recurring pattern — demand holding while solar drops — was the "
                "defining feature of the 2023 summer stress events."
            ),
            "raw_snapshot": {},
        },
    ]

    for event in events:
        try:
            save_event(event)
        except Exception:
            logger.exception("Failed to seed demo event")


app.mount(
    "/",
    StaticFiles(directory="frontend", html=True),
    name="frontend",
)
