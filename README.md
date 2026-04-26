# ERCOT Grid Stress Analyzer

**Team:** Jen Shi
**Track:** Energy / Infrastructure

---

## What We Built

A real-time monitoring, historical analysis, and ML-powered demand prediction tool for the Texas (ERCOT) power grid. It answers one question: **when conditions looked like this in the past, did the grid hold or did it fail — and what made the difference?**

Texas has had four catastrophic grid failures (1989, 2006, 2011, 2021). Three had the same root cause. Each time, the fix was recommended and ignored. Winter Storm Uri in 2021 was the worst grid failure in US history — 4.5 million customers lost power, and the grid was 4 minutes and 37 seconds from total collapse.

This tool makes those patterns impossible to miss.

### The Four Layers

**1. Live Monitoring** — Six key grid health metrics (forecast error, error growth rate, reserve margin, PRC, thermal outages, reserve price adder) updated every few minutes from real ERCOT data. A composite stress score (0-100) summarizes overall grid health. Error decomposition breaks the forecast gap into root causes (wind shortfall, solar shortfall, thermal outages, temperature-driven demand). Real-time fuel mix shows where power is coming from. When current conditions resemble a known historical failure, a fingerprint alert surfaces immediately.

**2. LSTM Demand Forecast** — A deep learning model trained on 5 years of ERCOT hourly load data (2021-2025) and Dallas weather history. Predicts grid demand at +1h, +4h, and +12h horizons plus stress event probability. 38 engineered features including zone loads, cyclical time encoding, lagged demand, rolling statistics, and weather. 2-layer LSTM, 282K parameters, trained in under 8 minutes on Apple Silicon. Predictions are displayed alongside ERCOT's own real-time forecast for direct comparison.

**3. Historical Survival Analysis** — 100+ labeled peak stress periods from 2003-2026, each classified by outcome (catastrophic / near-miss / managed / normal). Given current conditions, finds the most similar historical periods and reports: what percentage failed, what percentage survived, and what specific factors separated the two groups. Pattern threads trace recurring causal chains across decades.

**4. Automatic Event Logging** — Every stress event is captured as a structured post-mortem with cause classification, fingerprint match, response time tracking, and an AI-generated plain-language summary via Claude API. No manual reports — automatic institutional memory.

---

## Datasets and APIs

| Source | What | How |
|--------|------|-----|
| **ERCOT via gridstatus** (Python library) | Real-time load, reserves, outages, wind/solar, fuel mix + hourly load archive 2003-present | Free, open-source |
| **Open-Meteo** | Historical and current weather (temperature, humidity, wind) for Dallas, TX | Free, no API key |
| **FERC/NERC Joint Reports** | Post-mortem data from catastrophic grid failures | Public federal documents |
| **ERCOT Seasonal Assessments** | Reserve margins, demand forecasts, risk probabilities | Public ERCOT publications |
| **Supabase** (PostgreSQL) | Storage for snapshots, events, historical periods | Free tier |
| **Anthropic Claude API** | Plain-language event summaries | API key required |

The ML model was trained on 43,800 hours of ERCOT load data (8 weather zones + system total) merged with hourly weather observations from Open-Meteo, all downloaded and cached locally as Parquet files.

---

## How to Run It

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
git clone https://github.com/jenzshi/Grid-Scan.git
cd Grid-Scan

pip install -r requirements.txt
```

Create a `.env` file (optional — the app runs in mock mode without credentials):

```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
ANTHROPIC_API_KEY=your_anthropic_key
MOCK_MODE=true
```

### Train the ML Model

```bash
python -m backend.ml.train_pipeline
```

This downloads 5 years of ERCOT data + weather, engineers features, and trains the LSTM. Takes ~8 minutes. Checkpoint saves to `data/cache/demand_model.pt`.

### Start the App

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8200
```

Open **http://localhost:8200** in your browser.

### Run Tests

```bash
python -m pytest tests/ -v
```

---

## Tech Stack

- **Backend**: Python, FastAPI
- **ML**: PyTorch (LSTM), scikit-learn, pandas
- **Data**: gridstatus, Open-Meteo, Supabase (PostgreSQL)
- **AI**: Anthropic Claude API (event summaries only)
- **Frontend**: Vanilla HTML/CSS/JS, no framework, no build step
- **Charts**: Hand-drawn on HTML Canvas with interactive tooltips

---

## Project Structure

```
backend/
  main.py              # FastAPI app, polling loop
  config.py            # Thresholds, 15 historical fingerprints
  analysis/            # Forecast error, classifier, fingerprinter, survival analysis
  data/                # ERCOT + weather data clients
  ml/                  # LSTM model, training pipeline, inference
    data_downloader.py # Download + cache ERCOT/weather data
    historical_features.py  # 38-feature engineering pipeline
    model.py           # DemandLSTM architecture
    trainer.py         # Training loop, checkpointing
    train_pipeline.py  # End-to-end orchestrator
    inference.py       # Load model, serve predictions
  routes/              # API endpoints (live, events, trends, history, predictions)
  storage/             # Supabase client
frontend/
  index.html           # Single page app
  css/styles.css       # Light theme, clean typography
  js/                  # Router, views (live, history, trends, events), components
tests/                 # 89 tests across 15 files
```
