"""Dashboard API + static frontend. Reads paper-trading history from SQLite.

Run with: uvicorn dashboard.server:app --reload --port 8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dashboard.stats import compute_stats
from storage.db import get_bot_status, get_equity_snapshots, get_retune_events, get_trades, init_db

app = FastAPI(title="TradingBot Dashboard")

init_db()

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/status")
def api_status():
    return get_bot_status()


@app.get("/api/equity")
def api_equity(limit: int = 5000):
    return get_equity_snapshots(limit=limit)


@app.get("/api/trades")
def api_trades(limit: int = 500):
    return get_trades(limit=limit)


@app.get("/api/retunes")
def api_retunes(limit: int = 100):
    return get_retune_events(limit=limit)


@app.get("/api/stats")
def api_stats():
    return compute_stats(get_equity_snapshots(), get_trades(limit=100_000))


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
