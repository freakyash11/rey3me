"""Pull January 2026 WIND actuals and forecasts from Elexon into backend/data/snapshot.json.gz.

Scope: purchase decisions made 1-31 Jan 2026 -> delivery days 2 Jan - 1 Feb 2026.
December 2025 is included only as history: the uncertainty band shown for a
delivery day is calibrated on the ~4 weeks *before* the decision (no lookahead),
which for early-January decisions means December data. Forecast runs start 3
days before the first actual so every target hour has 48h+ horizons available.

Usage (from repo root):  python -m backend.scripts.build_snapshot
"""
from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import date, datetime, timezone

from backend.app import elexon
from backend.app.store import SNAPSHOT_PATH

ACTUALS_FROM, ACTUALS_TO = date(2025, 12, 1), date(2026, 2, 1)
FORECASTS_FROM = datetime(2025, 11, 28, tzinfo=timezone.utc)
FORECASTS_TO = datetime(2026, 2, 2, tzinfo=timezone.utc)


def main() -> None:
    actuals = elexon.fetch_actuals(ACTUALS_FROM, ACTUALS_TO)
    forecasts = elexon.fetch_forecasts(FORECASTS_FROM, FORECASTS_TO)

    actuals = [{k: r[k] for k in ("startTime", "publishTime", "generation")} for r in actuals]
    forecasts = [{k: r[k] for k in ("publishTime", "startTime", "generation")} for r in forecasts]

    runs = Counter(r["publishTime"] for r in forecasts)
    print(f"actuals: {len(actuals)} rows (expected {48 * ((ACTUALS_TO - ACTUALS_FROM).days + 1)})")
    print(f"forecasts: {len(forecasts)} rows across {len(runs)} runs")
    times = sorted(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in runs)
    gaps = [(a, b) for a, b in zip(times, times[1:]) if (b - a).total_seconds() > 6 * 3600]
    for a, b in gaps:
        print(f"  gap between runs: {a:%Y-%m-%d %H:%M} -> {b:%Y-%m-%d %H:%M}")

    snap = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actuals": actuals,
        "forecasts": forecasts,
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(SNAPSHOT_PATH, "wt", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))
    print(f"wrote {SNAPSHOT_PATH} ({SNAPSHOT_PATH.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
