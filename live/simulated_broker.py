"""A broker-free "paper" trading backend.

Mimics the subset of OandaClient's interface that live/paper_trader.py uses,
but never talks to a real broker account. Price data comes from Yahoo
Finance (no signup, no API key, no KYC); "orders" are just bookkeeping --
balance, position size, and entry price are tracked in the bot_status table
in SQLite, and fills happen at the latest Yahoo Finance price with a
simulated spread cost.

The spread cost scales with recent volatility (spread_bps as a floor, plus
slippage_atr_multiplier x the current ATR-as-a-%-of-price) rather than
being a flat number -- real bid/ask spreads and execution slippage widen in
volatile conditions and tighten in calm ones; a flat cost assumption is
optimistic exactly when it matters most (a strategy that only shows an edge
under a flat-cost assumption doesn't have a very robust one).
"""
from __future__ import annotations

import time

import pandas as pd

from data.fetch import fetch_yfinance_candles
from live.position_sizing import average_true_range
from storage.db import get_sim_state, reset_sim_state, set_sim_state


class SimulatedBroker:
    def __init__(
        self,
        instrument: str,
        granularity: str,
        starting_balance: float = 10_000.0,
        spread_bps: float = 2.0,
        slippage_atr_multiplier: float = 0.5,
    ):
        self.instrument = instrument
        self.granularity = granularity
        self.spread_bps = spread_bps
        self.slippage_atr_multiplier = slippage_atr_multiplier
        if get_sim_state()["sim_balance"] <= 0:
            reset_sim_state(starting_balance)

    def _price_and_vol_pct(self) -> tuple[float, float]:
        """(latest close price, recent volatility as ATR / price). Fetches
        enough bars for a real ATR reading, not just the latest close."""
        df = fetch_yfinance_candles(self.instrument, self.granularity, count=20)
        price = float(df["close"].iloc[-1])
        if len(df) < 2:
            return price, 0.0
        atr_series = average_true_range(df, period=min(14, len(df) - 1))
        atr = atr_series.iloc[-1]
        vol_pct = float(atr / price) if price > 0 and not pd.isna(atr) else 0.0
        return price, vol_pct

    def _latest_price(self) -> float:
        return self._price_and_vol_pct()[0]

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

        price, vol_pct = self._price_and_vol_pct()
        effective_spread_bps = self.spread_bps + self.slippage_atr_multiplier * vol_pct * 10_000
        spread_cost = price * (effective_spread_bps / 10_000.0)
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
