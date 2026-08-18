"""Tiny SQLite storage for paper-trading history, read by the dashboard."""
from __future__ import annotations

import datetime as dt
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    strategy TEXT NOT NULL,
    instrument TEXT NOT NULL,
    balance REAL NOT NULL,
    unrealized_pnl REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    strategy TEXT NOT NULL,
    instrument TEXT NOT NULL,
    side TEXT NOT NULL,
    units INTEGER NOT NULL,
    price REAL NOT NULL,
    pnl REAL,
    oanda_order_id TEXT
);

CREATE TABLE IF NOT EXISTS bot_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    strategy TEXT,
    instrument TEXT,
    params_json TEXT,
    running INTEGER NOT NULL DEFAULT 0,
    last_heartbeat TEXT,
    sim_balance REAL NOT NULL DEFAULT 10000,
    sim_position_units REAL NOT NULL DEFAULT 0,
    sim_entry_price REAL NOT NULL DEFAULT 0,
    last_retune_at TEXT
);

CREATE TABLE IF NOT EXISTS retune_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    old_strategy TEXT,
    old_params_json TEXT,
    new_strategy TEXT NOT NULL,
    new_params_json TEXT NOT NULL,
    mean_test_sharpe REAL,
    overfit_gap REAL,
    changed INTEGER NOT NULL DEFAULT 0
);
"""


def get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO bot_status (id, running) VALUES (1, 0)")
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(bot_status)")}
        for col, default in (("sim_balance", 10000), ("sim_position_units", 0), ("sim_entry_price", 0)):
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE bot_status ADD COLUMN {col} REAL NOT NULL DEFAULT {default}")
        if "last_retune_at" not in existing_cols:
            conn.execute("ALTER TABLE bot_status ADD COLUMN last_retune_at TEXT")


def record_equity_snapshot(strategy: str, instrument: str, balance: float, unrealized_pnl: float = 0.0) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO equity_snapshots (timestamp, strategy, instrument, balance, unrealized_pnl) "
            "VALUES (?, ?, ?, ?, ?)",
            (dt.datetime.utcnow().isoformat(), strategy, instrument, balance, unrealized_pnl),
        )


def record_trade(
    strategy: str,
    instrument: str,
    side: str,
    units: int,
    price: float,
    pnl: float | None = None,
    oanda_order_id: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO trades (timestamp, strategy, instrument, side, units, price, pnl, oanda_order_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (dt.datetime.utcnow().isoformat(), strategy, instrument, side, units, price, pnl, oanda_order_id),
        )


def set_bot_status(strategy: str, instrument: str, params_json: str, running: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE bot_status SET strategy=?, instrument=?, params_json=?, running=?, last_heartbeat=? "
            "WHERE id=1",
            (strategy, instrument, params_json, int(running), dt.datetime.utcnow().isoformat()),
        )


def heartbeat() -> None:
    with get_conn() as conn:
        conn.execute("UPDATE bot_status SET last_heartbeat=? WHERE id=1", (dt.datetime.utcnow().isoformat(),))


def get_sim_state() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT sim_balance, sim_position_units, sim_entry_price FROM bot_status WHERE id=1"
        ).fetchone()
        return dict(row) if row else {"sim_balance": 10000, "sim_position_units": 0, "sim_entry_price": 0}


def set_sim_state(balance: float, position_units: float, entry_price: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE bot_status SET sim_balance=?, sim_position_units=?, sim_entry_price=? WHERE id=1",
            (balance, position_units, entry_price),
        )


def reset_sim_state(starting_balance: float = 10_000.0) -> None:
    set_sim_state(starting_balance, 0, 0)


def get_last_retune_at() -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT last_retune_at FROM bot_status WHERE id=1").fetchone()
        return row["last_retune_at"] if row else None


def set_last_retune_at(timestamp_iso: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE bot_status SET last_retune_at=? WHERE id=1", (timestamp_iso,))


def get_bot_status() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bot_status WHERE id=1").fetchone()
        return dict(row) if row else {}


def get_equity_snapshots(limit: int = 5000) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_trades(limit: int = 500) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def record_retune_event(
    old_strategy: str | None,
    old_params_json: str | None,
    new_strategy: str,
    new_params_json: str,
    mean_test_sharpe: float | None,
    overfit_gap: float | None,
    changed: bool,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO retune_events "
            "(timestamp, old_strategy, old_params_json, new_strategy, new_params_json, "
            "mean_test_sharpe, overfit_gap, changed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                dt.datetime.utcnow().isoformat(),
                old_strategy,
                old_params_json,
                new_strategy,
                new_params_json,
                mean_test_sharpe,
                overfit_gap,
                int(changed),
            ),
        )


def get_retune_events(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM retune_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
