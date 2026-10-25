from datetime import date, timedelta

import pandas as pd
import pytest

from backend.app import forecast as fcast
from backend.app import metrics
from backend.app.store import rows_to_frames

T = pd.Timestamp


def make_frames():
    """Two days of flat actuals and three forecast runs with distinguishable values."""
    actual_rows = [
        {"startTime": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "publishTime": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "generation": 1000}
        for t in pd.date_range("2026-01-14", "2026-01-15 23:30", freq="30min", tz="UTC")
    ]
    forecast_rows = []
    for published, value in [("2026-01-13T22:30:00Z", 1100), ("2026-01-14T07:30:00Z", 1200), ("2026-01-14T09:30:00Z", 1300)]:
        for t in pd.date_range(published, periods=73, freq="h", tz="UTC").ceil("h"):
            forecast_rows.append({"publishTime": published, "startTime": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "generation": value})
    return rows_to_frames(actual_rows, forecast_rows)


def test_latest_run_is_inclusive_of_cutoff():
    _, fc = make_frames()
    assert fcast.latest_run_at(fc, T("2026-01-14T07:30Z")) == T("2026-01-14T07:30Z")
    assert fcast.latest_run_at(fc, T("2026-01-14T07:29Z")) == T("2026-01-13T22:30Z")
    assert fcast.latest_run_at(fc, T("2026-01-14T09:00Z")) == T("2026-01-14T07:30Z")
    assert fcast.latest_run_at(fc, T("2026-01-01T00:00Z")) is None


def test_run_for_day_covers_24_hours():
    _, fc = make_frames()
    vals = fcast.run_for_day(fc, T("2026-01-14T07:30Z"), date(2026, 1, 15))
    assert len(vals) == 24 and set(vals) == {1200}


def test_day_bounds_handles_dst():
    start, end = fcast.day_bounds(date(2026, 3, 29))  # clocks go forward: 23h day
    assert (end - start) == pd.Timedelta(hours=23)


def test_horizon_alignment_never_uses_future_runs():
    act, fc = make_frames()
    aligned = fcast.horizon_aligned(fc, act, horizon_h=24)
    # Only hourly targets are compared.
    assert (aligned["start"].dt.minute == 0).all()
    # Every pairing respects the horizon.
    assert ((aligned["start"] - aligned["published"]) >= pd.Timedelta(hours=24)).all()
    # Target 2026-01-15 09:00 with H=24 -> cutoff 2026-01-14 09:00 -> 07:30 run.
    row = aligned[aligned["start"] == T("2026-01-15T09:00Z")].iloc[0]
    assert row["published"] == T("2026-01-14T07:30Z") and row["forecast"] == 1200


def test_decision_backtest_matches_rule():
    act, fc = make_frames()
    bt = fcast.decision_backtest(fc, act, [date(2026, 1, 15)], lead=timedelta(hours=15))  # D-1 09:00
    assert len(bt) == 24 and set(bt["forecast"]) == {1200} and set(bt["actual"]) == {1000}


def test_duplicate_actuals_keep_latest_publish():
    rows = [
        {"startTime": "2026-01-14T00:00:00Z", "publishTime": "2026-01-14T00:30:00Z", "generation": 1},
        {"startTime": "2026-01-14T00:00:00Z", "publishTime": "2026-01-14T01:30:00Z", "generation": 2},
    ]
    act, _ = rows_to_frames(rows, [])
    assert act["generation"].tolist() == [2.0]


def test_summary_metrics_by_hand():
    m = metrics.summary(pd.Series([110.0, 90.0, 1300.0, 1000.0]), pd.Series([100.0, 100.0, 1000.0, 1000.0]))
    assert m["n"] == 4
    assert m["mae"] == pytest.approx((10 + 10 + 300 + 0) / 4)
    assert m["bias"] == pytest.approx((10 - 10 + 300 + 0) / 4)
    assert m["rmse"] == pytest.approx(((100 + 100 + 90000 + 0) / 4) ** 0.5)
    # MAPE only over actuals >= 1000 MW: (300/1000 + 0/1000) / 2
    assert m["mape"] == pytest.approx(15.0)


def test_histogram_counts_everything():
    errors = pd.Series([-900, -100, 0, 400, 1600])
    bins = metrics.histogram(errors, bin_mw=500)
    assert sum(b["count"] for b in bins) == len(errors)
