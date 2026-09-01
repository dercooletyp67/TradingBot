"""A broker-free "paper" trading backend.

Mimics the subset of OandaClient's interface that live/paper_trader.py uses,
but never talks to a real broker account. Price data comes from Yahoo
Finance (no signup, no API key, no KYC); "orders" are just bookkeeping --
balance, position size, and entry price are tracked in the bot_status table
in SQLite, and fills happen at the latest Yahoo Finance price with a small
simulated spread cost.
"""
from __future__ import annotations

import time

from data.fetch import fetch_yfinance_candles
from storage.db import get_sim_state, reset_sim_state, set_sim_state


class SimulatedBroker:
    def __init__(
        self,
        instrument: str,
        granularity: str,
        starting_balance: float = 10_000.0,
        spread_bps: float = 2.0,
    ):
        self.instrument = instrument
        self.granularity = granularity
        self.spread_bps = spread_bps
        if get_sim_state()["sim_balance"] <= 0:
            reset_sim_state(starting_balance)

    def _latest_price(self) -> float:
        df = fetch_yfinance_candles(self.instrument, self.granularity, count=2)
        return float(df["close"].iloc[-1])

    def get_account_summary(self) -> dict:
        state = get_sim_state()
        balance, units, entry = state["sim_balance"], state["sim_position_units"], state["sim_entry_price"]
        unrealized = units * (self._latest_price() - entry) if units != 0 else 0.0
        return {"balance": balance, "unrealizedPL": unrealized}

    def get_open_units(self, instrument: str) -> float:
        # Fractional, deliberately -- a whole-unit floor is fine for forex
        # (1 unit of EUR is ~$1) but breaks high-priced assets like BTC-USD,
        # where a sane risk-sized position is routinely well under 1 unit.
        return float(get_sim_state()["sim_position_units"])

    def get_recent_candles(self, instrument: str, granularity: str, count: int):
        return fetch_yfinance_candles(instrument, granularity, count=count)

    def place_market_order(self, instrument: str, units: float) -> dict:
        state = get_sim_state()
        balance, pos, entry = state["sim_balance"], state["sim_position_units"], state["sim_entry_price"]

        price = self._latest_price()
        spread_cost = price * (self.spread_bps / 10_000.0)
        fill_price = price + spread_cost if units > 0 else price - spread_cost

        new_pos = pos + units
        new_entry = entry
        realized_pnl = 0.0

        if pos == 0:
            new_entry = fill_price
        elif (pos > 0 and units > 0) or (pos < 0 and units < 0):
            new_entry = (entry * abs(pos) + fill_price * abs(units)) / abs(new_pos)
        else:
            closing_units = min(abs(units), abs(pos))
            direction = 1 if pos > 0 else -1
            realized_pnl = closing_units * direction * (fill_price - entry)
            balance += realized_pnl
            if new_pos == 0:
                new_entry = 0
            elif (new_pos > 0) != (pos > 0):
                new_entry = fill_price  # flipped through zero
            else:
                new_entry = entry

        set_sim_state(balance, new_pos, new_entry)

        return {
            "orderFillTransaction": {
                "price": fill_price,
                "id": f"sim-{int(time.time() * 1000)}",
                "pl": realized_pnl,
            }
        }
