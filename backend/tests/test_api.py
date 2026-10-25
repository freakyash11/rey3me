"""Route tests against the bundled January 2026 snapshot (no network)."""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_and_meta():
    assert client.get("/api/health").json() == {"status": "ok"}
    meta = client.get("/api/meta").json()
    assert meta["scope"] == {"from": "2026-01-02", "to": "2026-02-01"}
    assert "2026-01-15" in meta["actualDays"]


def test_day_ahead_default_decision():
    body = client.get("/api/dayahead", params={"date": "2026-01-15"}).json()
    assert body["decision"] == "2026-01-14T09:00:00Z"
    assert body["run"]["published"] <= body["decision"]
    assert body["run"]["hours"] == 24
    assert body["calibration"]["to"] <= "2026-01-13"  # no lookahead into D-1
    forecasts = [p for p in body["series"] if p["forecast"] is not None]
    assert all(p["low"] <= p["forecast"] <= p["high"] for p in forecasts)


def test_day_ahead_rejects_decision_after_delivery_start():
    r = client.get("/api/dayahead", params={"date": "2026-01-15", "decision": "2026-01-15T09:00"})
    assert r.status_code == 400


def test_accuracy_and_horizons():
    acc = client.get("/api/accuracy", params={"horizon": 24}).json()
    assert acc["metrics"]["n"] > 700
    hz = client.get("/api/accuracy/horizons").json()
    assert [h["horizon"] for h in hz["horizons"]] == list(range(49))
    assert hz["dayAheadRule"]["n"] > 700
