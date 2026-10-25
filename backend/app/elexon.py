"""Thin client for the Elexon BMRS Insights API (no API key required)."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import httpx

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
# The stream endpoints happily return a week of WINDFOR runs (~4k rows) per call.
FORECAST_CHUNK = timedelta(days=7)
ACTUALS_CHUNK_DAYS = 31


def _get(client: httpx.Client, path: str, params: dict, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        try:
            resp = client.get(f"{BASE_URL}/{path}", params=params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return []


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_actuals(start: date, end: date, client: httpx.Client | None = None) -> list[dict]:
    """Half-hourly WIND outturn (FUELHH) for settlement dates start..end inclusive."""
    own = client is None
    client = client or httpx.Client(timeout=60)
    rows: list[dict] = []
    try:
        cur = start
        while cur <= end:
            chunk_end = min(end, cur + timedelta(days=ACTUALS_CHUNK_DAYS - 1))
            rows += _get(
                client,
                "FUELHH/stream",
                {
                    "settlementDateFrom": cur.isoformat(),
                    "settlementDateTo": chunk_end.isoformat(),
                    "fuelType": "WIND",
                },
            )
            cur = chunk_end + timedelta(days=1)
    finally:
        if own:
            client.close()
    return rows


def fetch_forecasts(start: datetime, end: datetime, client: httpx.Client | None = None) -> list[dict]:
    """Hourly WINDFOR forecast rows whose publishTime falls in [start, end)."""
    own = client is None
    client = client or httpx.Client(timeout=60)
    rows: list[dict] = []
    try:
        cur = start
        while cur < end:
            chunk_end = min(end, cur + FORECAST_CHUNK)
            batch = _get(
                client,
                "WINDFOR/stream",
                {"publishDateTimeFrom": _iso(cur), "publishDateTimeTo": _iso(chunk_end)},
            )
            # Range bounds are inclusive on the API side; keep [cur, chunk_end) to avoid duplicates.
            rows += [r for r in batch if r["publishTime"] < _iso(chunk_end) or chunk_end == end]
            cur = chunk_end
    finally:
        if own:
            client.close()
    return rows
