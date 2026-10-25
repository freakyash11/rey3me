# Wind Forecast Monitor

A web app for a UK utility's **day-ahead power-buying team**. It answers two questions for every delivery day:

1. **What wind generation was forecast when we had to decide?** It shows the latest Elexon wind forecast published before the trader's decision time (default 09:00 on D-1, adjustable) against what was actually generated.
2. **How far can we trust that forecast?** It quantifies forecast error (MAE, RMSE, bias, P10/P90, error vs horizon, daily error). It also turns the error into a **"firm wind" estimate**: wind output we can rely on with 90% confidence. The rest of the requirement is bought day-ahead.

**Live app:** _VERCEL_URL_

Scope: national GB wind only, from Elexon BMRS:
- [FUELHH](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream) gives half-hourly actual generation (fuelType `WIND`).
- [WINDFOR](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream) gives hourly forecasts. A new run is published about 8 times a day, and each run looks about 72h ahead.

The data covers purchase decisions made in **January 2026**, i.e. delivery days 2 Jan – 1 Feb 2026.

## Repository layout

| Path | What it is |
|---|---|
| `backend/app/main.py` | FastAPI app. All routes live under `/api` (see [API](#api)). |
| `backend/app/forecast.py` | Forecast-selection logic: *decision view* (latest run published ≤ decision time) and *horizon view* (latest run published ≤ target − H). |
| `backend/app/metrics.py` | Error metrics: MAE, RMSE, bias, MAPE, percentiles, histogram, daily MAE. |
| `backend/app/store.py` | Loads the bundled data snapshot. Fetches days outside it live from Elexon and caches them in memory. |
| `backend/app/elexon.py` | Minimal Elexon BMRS client (chunked requests, retries). |
| `backend/scripts/build_snapshot.py` | Regenerates `backend/data/snapshot.json.gz` from the Elexon API. |
| `backend/data/snapshot.json.gz` | Wind actuals (1 Dec 2025 – 1 Feb 2026) and every WINDFOR run published from 28 Nov 2025 – 1 Feb 2026 (~225 KB). |
| `backend/tests/` | pytest suite: selection rules, metric arithmetic, API routes. |
| `backend/Dockerfile` | Backend image (uvicorn on :8000). |
| `frontend/src/pages/DayAhead.tsx` | **Day-ahead view**: delivery day + decision time → forecast, uncertainty band, firm wind, actuals. |
| `frontend/src/pages/Accuracy.tsx` | **Forecast accuracy**: horizon slider and date range → metrics, error-vs-horizon, error histogram, daily MAE. |
| `frontend/src/api.ts`, `format.ts`, `components/` | Typed API client, formatting helpers, shared tiles and tooltips. |
| `frontend/Dockerfile`, `frontend/nginx.conf` | Builds the React app and serves it with nginx. nginx proxies `/api` to the backend. |
| `docker-compose.yml` | Runs both containers locally. |
| `api/index.py`, `vercel.json` | Vercel deployment: the static React build plus FastAPI as a Python serverless function. |
| `requirements.txt`, `requirements-dev.txt` | Python runtime and dev (pytest) dependencies. |

## Running it

### With Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:8080. The API is also exposed directly on http://localhost:8000/api/health.

### Without Docker (development)

```bash
# backend (Python 3.12)
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn backend.app.main:app --reload --port 8000

# frontend (Node 20), in a second terminal
cd frontend && npm install && npm run dev            # http://localhost:5173, proxies /api to :8000
```

### Tests

```bash
python -m pytest backend/tests
```

### Refreshing the data snapshot

```bash
python -m backend.scripts.build_snapshot
```

The script prints row and run counts and reports any gap between forecast runs longer than 6h.

### Deploying to Vercel

```bash
vercel --prod
```

`vercel.json` builds `frontend/` as a static site and deploys `api/index.py` (FastAPI) as a Python function, bundled with `backend/app` and `backend/data`.

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness check. |
| `GET /api/meta` | Data source, scope, days with actuals, forecast-run coverage. |
| `GET /api/dayahead?date=2026-01-15[&decision=2026-01-14T09:00]` | Forecast available at the decision time (London local) for the delivery day, actuals, P10–P90 band, firm-wind energy, run age, next run, and the day's realised error. |
| `GET /api/accuracy?horizon=24[&from=2026-01-02&to=2026-02-01]` | Hourly forecast/actual pairs at a fixed horizon, with summary metrics, error histogram and daily MAE. |
| `GET /api/accuracy/horizons[?from=&to=]` | MAE, RMSE, bias and P90 absolute error for horizons 0–48h, plus the D-1 09:00 decision rule evaluated over the same days. |

Interactive docs: `/docs` when running the backend locally.

## Method and assumptions

- **Which forecast counts.** A forecast is usable only if its `publishTime` is at or before the decision time (or before `target − H`). The latest such run wins. This mirrors what a trader could actually have seen, with no hindsight.
- **Default decision time is 09:00 UK on D-1.** This is ahead of the GB day-ahead auction gate closures. It can be changed in the UI (any time, D-1 or D-2). At 09:00 the latest run is the 07:30 one, and a fresher run lands at 09:30. The UI shows this so traders can see the value of waiting.
- **Alignment.** WINDFOR is hourly and FUELHH is half-hourly, so errors are computed on the on-the-hour periods. Charts still show half-hourly actuals.
- **Error = forecast − actual.** A positive value means the forecast was too high (over-forecast).
- **Uncertainty band and firm wind.** For delivery day D, the decision rule (same lead time) is replayed over the 28 days ending D-2. D-2 is the last day whose actuals were complete at decision time, so there is no lookahead. The P10/P90 of those errors give the band:
  - actual ∈ [forecast − P90, forecast − P10];
  - firm wind = forecast − P90 error, floored at 0.

  This is why the snapshot includes December 2025 history.
- **MAPE** excludes hours with actual < 1 GW, where percentage error is meaningless.
- **Timezone.** Delivery days are Europe/London calendar days. DST is handled, although January is GMT.
- **Data freshness.** The snapshot makes the deployed demo fast and independent of Elexon uptime. Requests for days outside it (2023 onwards) are fetched live from Elexon and cached.

### What January 2026 shows

- At the D-1 09:00 decision, the forecast's mean absolute error was **~2.0 GW**, against an average wind output of ~11.3 GW.
- The forecast was biased **high by ~1.7 GW**. Wind delivered less than forecast in most hours.
- Error grows from ~1.7 GW MAE at 0h ahead to ~2.3 GW at 48h ahead.

## AI tools

This project was built with the help of **Claude Code** (Anthropic's AI coding assistant). It was used for API exploration, code generation (backend, frontend, Docker and Vercel configuration), tests and documentation. All outputs were reviewed, run and verified against the live Elexon data.
