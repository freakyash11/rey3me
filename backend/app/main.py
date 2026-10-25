"""FastAPI app: day-ahead wind forecast view and forecast-accuracy analytics."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import forecast as fcast
from . import metrics
from .store import get_store

app = FastAPI(title="Wind Forecast Monitor API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

# Scope: purchase decisions made during January 2026 -> delivery days 2 Jan .. 1 Feb.
SCOPE_FROM, SCOPE_TO = date(2026, 1, 2), date(2026, 2, 1)
DEFAULT_DECISION_TIME = time(9, 0)  # D-1, London time; ahead of the GB day-ahead auction gate closures
EARLIEST_LIVE_DAY = date(2023, 1, 1)


def iso(ts: pd.Timestamp | None) -> str | None:
    return None if ts is None or pd.isna(ts) else ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(x):
    """Round floats for compact JSON and map NaN to null."""
    if isinstance(x, float):
        return None if np.isnan(x) else round(x, 1)
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean(v) for v in x]
    return x


def _data_version() -> tuple[int, int]:
    s = get_store()
    return len(s.actuals), len(s.forecasts)


@lru_cache(maxsize=64)
def _backtest(lead_seconds: int, version: tuple[int, int]) -> pd.DataFrame:
    s = get_store()
    return fcast.decision_backtest(s.forecasts, s.actuals, s.actual_days(), timedelta(seconds=lead_seconds))


@lru_cache(maxsize=256)
def _aligned(horizon_h: float, start: date, end: date, version: tuple[int, int]) -> pd.DataFrame:
    s = get_store()
    lo, _ = fcast.day_bounds(start)
    _, hi = fcast.day_bounds(end)
    return fcast.horizon_aligned(s.forecasts, s.actuals, horizon_h, lo, hi)


def _parse_range(from_: date | None, to: date | None) -> tuple[date, date]:
    start, end = from_ or SCOPE_FROM, to or SCOPE_TO
    if end < start:
        raise HTTPException(400, "`to` must not be before `from`")
    if (end - start).days > 120:
        raise HTTPException(400, "date range limited to 120 days")
    return start, end


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    s = get_store()
    runs = s.publish_times()
    return {
        "source": s.source,
        "scope": {"from": SCOPE_FROM.isoformat(), "to": SCOPE_TO.isoformat()},
        "defaultDecisionTime": DEFAULT_DECISION_TIME.strftime("%H:%M"),
        "actualDays": [d.isoformat() for d in s.actual_days()],
        "forecastRuns": {"count": len(runs), "first": iso(runs.min()), "last": iso(runs.max())},
    }


@app.get("/api/dayahead")
def day_ahead(
    day: date = Query(..., alias="date", description="Delivery day (London)"),
    decision: datetime | None = Query(None, description="Decision time, London local (default D-1 09:00)"),
):
    if not (EARLIEST_LIVE_DAY <= day <= date.today() + timedelta(days=1)):
        raise HTTPException(400, "date out of supported range")
    decision = decision or datetime.combine(day - timedelta(days=1), DEFAULT_DECISION_TIME)
    if decision.tzinfo is None:
        decision = decision.replace(tzinfo=fcast.LONDON)
    decision_ts = pd.Timestamp(decision).tz_convert("UTC")
    day_start, day_end = fcast.day_bounds(day)
    if decision_ts > day_start:
        raise HTTPException(400, "decision time must be at or before the start of the delivery day")
    if decision_ts < day_start - timedelta(days=3):
        raise HTTPException(400, "decision time more than 3 days ahead is beyond the forecast horizon")

    s = get_store()
    try:
        s.ensure_day(day)
    except Exception as exc:  # live fallback failed; serve whatever we have
        if s.actuals.empty:
            raise HTTPException(502, f"Elexon fetch failed: {exc}") from exc

    published = fcast.latest_run_at(s.forecasts, decision_ts)
    if published is None:
        raise HTTPException(404, "no forecast was published before the decision time")
    fc = fcast.run_for_day(s.forecasts, published, day)
    later = s.publish_times()
    later = later[(later > decision_ts) & (later <= day_start)]

    # Uncertainty band calibrated on the same decision rule over the previous 4 weeks,
    # using only days whose actuals were complete by decision time (<= D-2): no lookahead.
    lead = day_start - decision_ts
    bt = _backtest(int(lead.total_seconds()), _data_version())
    calib = bt[(bt["day"] >= day - timedelta(days=fcast.CALIBRATION_DAYS + 1)) & (bt["day"] <= day - timedelta(days=2))]
    cal = metrics.summary(calib["forecast"], calib["actual"])

    acts = s.actuals[(s.actuals.index >= day_start) & (s.actuals.index < day_end)]["generation"]
    timeline = acts.index.union(fc.index)
    series = []
    for t in timeline:
        f = fc.get(t)
        row = {"time": iso(t), "actual": acts.get(t), "forecast": f, "low": None, "high": None}
        if f is not None and cal["n"]:
            row["low"] = max(0.0, f - cal["p90"])
            row["high"] = f - cal["p10"]
        series.append(row)

    day_metrics = None
    paired = pd.DataFrame({"forecast": fc, "actual": acts.reindex(fc.index)}).dropna()
    if len(paired):
        day_metrics = metrics.summary(paired["forecast"], paired["actual"])

    firm = (fc - cal["p90"]).clip(lower=0) if cal["n"] else None
    return clean(
        {
            "date": day.isoformat(),
            "decision": iso(decision_ts),
            "leadHours": lead.total_seconds() / 3600,
            "run": {
                "published": iso(published),
                "ageMinutes": (decision_ts - published).total_seconds() / 60,
                "hours": int(len(fc)),
                "nextRun": iso(later.min()) if len(later) else None,
                "runsBeforeDelivery": int(len(later)),
            },
            "forecastEnergyMWh": float(fc.sum()),  # hourly MW values -> MWh
            "firmEnergyMWh": float(firm.sum()) if firm is not None else None,
            "forecastMin": float(fc.min()) if len(fc) else None,
            "forecastMax": float(fc.max()) if len(fc) else None,
            "calibration": {
                "days": int(calib["day"].nunique()),
                "from": min(calib["day"]).isoformat() if len(calib) else None,
                "to": max(calib["day"]).isoformat() if len(calib) else None,
                **cal,
            },
            "dayMetrics": day_metrics,
            "series": series,
        }
    )


@app.get("/api/accuracy")
def accuracy(
    horizon: float = Query(24, ge=0, le=48, description="Forecast lead time in hours"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
):
    start, end = _parse_range(from_, to)
    aligned = _aligned(horizon, start, end, _data_version())
    return clean(
        {
            "horizon": horizon,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "metrics": metrics.summary(aligned["forecast"], aligned["actual"]),
            "histogram": metrics.histogram(aligned["error"]),
            "daily": metrics.daily_mae(aligned),
            "series": [
                {"time": iso(r.start), "forecast": r.forecast, "actual": r.actual, "published": iso(r.published)}
                for r in aligned.itertuples()
            ],
        }
    )


@app.get("/api/accuracy/horizons")
def accuracy_by_horizon(from_: date | None = Query(None, alias="from"), to: date | None = None):
    start, end = _parse_range(from_, to)
    version = _data_version()
    rows = []
    for h in range(0, 49):
        a = _aligned(float(h), start, end, version)
        m = metrics.summary(a["forecast"], a["actual"])
        rows.append({"horizon": h, **{k: m.get(k) for k in ("n", "mae", "rmse", "bias", "p90_abs")}})

    # The trader's actual rule: latest run before D-1 09:00, evaluated over the same days.
    lead = fcast.day_bounds(SCOPE_FROM)[0] - pd.Timestamp(
        datetime.combine(SCOPE_FROM - timedelta(days=1), DEFAULT_DECISION_TIME, tzinfo=fcast.LONDON)
    )
    bt = _backtest(int(lead.total_seconds()), version)
    bt = bt[(bt["day"] >= start) & (bt["day"] <= end)]
    return clean(
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "horizons": rows,
            "dayAheadRule": {
                "decisionTime": DEFAULT_DECISION_TIME.strftime("%H:%M"),
                **metrics.summary(bt["forecast"], bt["actual"]),
            },
        }
    )
