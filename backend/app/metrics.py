"""Forecast error metrics. Error convention: error = forecast - actual (positive = over-forecast)."""
from __future__ import annotations

import numpy as np
import pandas as pd

# MAPE is meaningless when actual wind output is near zero; skip those hours.
MAPE_MIN_ACTUAL_MW = 1000.0


def summary(forecast: pd.Series, actual: pd.Series) -> dict:
    f = np.asarray(forecast, dtype=float)
    a = np.asarray(actual, dtype=float)
    if f.size == 0:
        return {"n": 0}
    err = f - a
    abs_err = np.abs(err)
    mape_mask = a >= MAPE_MIN_ACTUAL_MW
    p10, p50, p90 = np.percentile(err, [10, 50, 90])
    return {
        "n": int(f.size),
        "mae": float(abs_err.mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "bias": float(err.mean()),
        "mape": float((abs_err[mape_mask] / a[mape_mask]).mean() * 100) if mape_mask.any() else None,
        "p10": float(p10),
        "p50": float(p50),
        "p90": float(p90),
        "p90_abs": float(np.percentile(abs_err, 90)),
        "max_abs": float(abs_err.max()),
        "mean_actual": float(a.mean()),
    }


def histogram(errors: pd.Series, bin_mw: int = 500) -> list[dict]:
    e = np.asarray(errors, dtype=float)
    if e.size == 0:
        return []
    lo = np.floor(e.min() / bin_mw) * bin_mw
    hi = np.ceil(e.max() / bin_mw) * bin_mw + bin_mw
    counts, edges = np.histogram(e, bins=np.arange(lo, hi + 1, bin_mw))
    return [{"from": float(edges[i]), "to": float(edges[i + 1]), "count": int(c)} for i, c in enumerate(counts)]


def daily_mae(aligned: pd.DataFrame) -> list[dict]:
    if aligned.empty:
        return []
    days = aligned["start"].dt.tz_convert("Europe/London").dt.date
    grouped = aligned.assign(day=days, abs_error=aligned["error"].abs()).groupby("day")
    return [
        {"day": d.isoformat(), "mae": float(g["abs_error"].mean()), "bias": float(g["error"].mean())}
        for d, g in grouped
    ]
