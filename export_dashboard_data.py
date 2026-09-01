"""Exports the current bot state as static JSON files under docs/<subdir>/,
for a GitHub Pages dashboard page -- which can't hit a live FastAPI server,
since GitHub Pages only serves static files.

Run this after a paper-trader tick, pointed at whichever DB you want to
publish (respects TRADINGBOT_DB_PATH / TRADINGBOT_LEARN_DIR, same as
everything else). TRADINGBOT_DOCS_SUBDIR picks which docs/ subfolder to
write to -- e.g. "data" for the EUR_USD instance (docs/index.html),
"data-btc" for the BTC-USD instance (docs/btc.html) -- see the .github/
workflows/*.yml files for each instance's exact usage.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from config import ROOT_DIR
from dashboard.stats import compute_stats
from storage.db import get_bot_status, get_equity_snapshots, get_retune_events, get_trades, init_db

DATA_DIR = ROOT_DIR / "docs" / os.getenv("TRADINGBOT_DOCS_SUBDIR", "data")


def export() -> None:
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    status = get_bot_status()
    equity = get_equity_snapshots()
    trades = get_trades(limit=1000)
    retunes = get_retune_events(limit=200)
    stats = compute_stats(equity, get_trades(limit=100_000))

    _write("status.json", status)
    _write("equity.json", equity)
    _write("trades.json", trades)
    _write("retunes.json", retunes)
    _write("stats.json", stats)
    print(f"Exported dashboard data to {DATA_DIR}")


def _write(filename: str, data) -> None:
    (DATA_DIR / filename).write_text(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    export()
