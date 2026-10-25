"""Forecast selection: which forecast was actually available when a decision was made.

Two views:
* decision view  - for delivery day D and a decision time T, use the latest
  WINDFOR run published at or before T (what a trader could have seen).
* horizon view   - for each target hour t and a horizon H, use the latest run
  published at or before t - H (classic lead-time accuracy analysis).

All timestamps are tz-aware UTC; delivery days are Europe/London calendar days.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

LONDON = ZoneInfo("Europe/London")
CALIBRATION_DAYS = 28


def day_bounds(day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """UTC [start, end) of a London calendar day (handles 23/25h DST days)."""
    start = pd.Timestamp(datetime.combine(day, time(0), tzinfo=LONDON)).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(day + timedelta(days=1), time(0), tzinfo=LONDON)).tz_convert("UTC")
    return start, end


def latest_run_at(forecasts: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Timestamp | None:
    """publishTime of the most recent run published at or before `cutoff`."""
    published = forecasts["published"]
    eligible = published[published <= cutoff]
    return None if eligible.empty else eligible.max()


def run_for_day(forecasts: pd.DataFrame, published: pd.Timestamp, day: date) -> pd.Series:
    """Hourly values of one run that fall inside the delivery day."""
    start, end = day_bounds(day)
    run = forecasts[(forecasts["published"] == published) & (forecasts["start"] >= start) & (forecasts["start"] < end)]
    return run.set_index("start")["generation"]


def decision_backtest(
    forecasts: pd.DataFrame, actuals: pd.DataFrame, days: list[date], lead: timedelta
) -> pd.DataFrame:
    """Apply the decision rule (decide `lead` before each day's start) over many days.

    Returns one row per delivery hour with the forecast available at decision
    time and the matching actual: columns day, start, forecast, actual.
    """
    frames = []
    for day in days:
        start, _ = day_bounds(day)
        published = latest_run_at(forecasts, start - lead)
        if published is None:
            continue
        fc = run_for_day(forecasts, published, day)
        frames.append(pd.DataFrame({"day": day, "start": fc.index, "forecast": fc.values}))
    if not frames:
        return pd.DataFrame(columns=["day", "start", "forecast", "actual"])
    out = pd.concat(frames, ignore_index=True)
    out["actual"] = out["start"].map(actuals["generation"])
    return out.dropna(subset=["actual"])


def horizon_aligned(
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    horizon_h: float,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Pair each hourly actual at t with the latest forecast for t published <= t - H.

    Forecasts are hourly while actuals are half-hourly, so comparison happens on
    the on-the-hour settlement periods only. Returns columns start, published,
    forecast, actual, error (forecast - actual).
    """
    act = actuals[actuals.index.minute == 0]
    if start is not None:
        act = act[act.index >= start]
    if end is not None:
        act = act[act.index < end]
    targets = pd.DataFrame({"start": act.index, "actual": act["generation"].values})
    targets["cutoff"] = targets["start"] - pd.Timedelta(hours=horizon_h)

    fc = forecasts.sort_values("published")
    merged = pd.merge_asof(
        targets.sort_values("cutoff"),
        fc.rename(columns={"generation": "forecast"}),
        left_on="cutoff",
        right_on="published",
        by="start",
        direction="backward",
    )
    merged = merged.dropna(subset=["forecast"]).sort_values("start").reset_index(drop=True)
    merged["error"] = merged["forecast"] - merged["actual"]
    return merged[["start", "published", "forecast", "actual", "error"]]
