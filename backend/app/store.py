"""In-memory data store: bundled January 2026 snapshot, with a live Elexon fallback.

The snapshot keeps serverless cold starts fast and the demo independent of
Elexon uptime. Requests outside the snapshot window are fetched live and cached
for the lifetime of the process.
"""
from __future__ import annotations

import gzip
import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import elexon

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "snapshot.json.gz"
# Forecast runs reach ~72h ahead, so covering a delivery day needs runs from 3 days before it.
FORECAST_LOOKBACK = timedelta(days=3)


def rows_to_frames(actual_rows: list[dict], forecast_rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalise raw API rows into tidy frames (UTC timestamps, deduplicated)."""
    act = pd.DataFrame(actual_rows, columns=["startTime", "publishTime", "generation"])
    act["start"] = pd.to_datetime(act["startTime"], utc=True)
    act["published"] = pd.to_datetime(act["publishTime"], utc=True)
    act = (
        act.sort_values("published")
        .drop_duplicates("start", keep="last")
        .set_index("start")
        .sort_index()[["generation"]]
        .astype(float)
    )

    fc = pd.DataFrame(forecast_rows, columns=["publishTime", "startTime", "generation"])
    fc = pd.DataFrame(
        {
            "published": pd.to_datetime(fc["publishTime"], utc=True),
            "start": pd.to_datetime(fc["startTime"], utc=True),
            "generation": fc["generation"].astype(float),
        }
    )
    fc = fc.drop_duplicates(["published", "start"], keep="last").sort_values(["published", "start"])
    return act, fc.reset_index(drop=True)


class Store:
    def __init__(self, actuals: pd.DataFrame, forecasts: pd.DataFrame, source: str):
        self.actuals = actuals
        self.forecasts = forecasts
        self.source = source
        self._lock = threading.Lock()
        self._fetched_days: set[date] = set()

    @classmethod
    def from_snapshot(cls, path: Path = SNAPSHOT_PATH) -> "Store":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            snap = json.load(f)
        return cls(*rows_to_frames(snap["actuals"], snap["forecasts"]), source=f"snapshot {snap['generatedAt']}")

    # --- coverage -----------------------------------------------------------------
    def actual_days(self) -> list[date]:
        days = pd.Series(self.actuals.index.date).value_counts()
        return sorted(d for d, n in days.items() if n >= 46)  # allow for a couple of missing periods

    def publish_times(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.forecasts["published"].unique()).sort_values()

    # --- live fallback --------------------------------------------------------------
    def ensure_day(self, day: date) -> None:
        """Make sure actuals and the forecasts relevant to `day` are loaded."""
        has_actuals = (pd.Series(self.actuals.index.date) == day).sum() >= 46
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        has_runs = (
            (self.forecasts["published"] >= day_start - FORECAST_LOOKBACK)
            & (self.forecasts["published"] < day_start)
        ).any()
        if (has_actuals and has_runs) or day in self._fetched_days:
            return
        with self._lock:
            if day in self._fetched_days:
                return
            self._fetched_days.add(day)
            act_rows = elexon.fetch_actuals(day, day)
            fc_rows = elexon.fetch_forecasts(day_start - FORECAST_LOOKBACK, day_start + timedelta(days=1))
            act, fc = rows_to_frames(act_rows, fc_rows)
            self.actuals = pd.concat([self.actuals, act])
            self.actuals = self.actuals[~self.actuals.index.duplicated(keep="last")].sort_index()
            self.forecasts = (
                pd.concat([self.forecasts, fc])
                .drop_duplicates(["published", "start"], keep="last")
                .sort_values(["published", "start"])
                .reset_index(drop=True)
            )


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store.from_snapshot()
    return _store
