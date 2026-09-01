"""Position sizing: how many units to trade, not which direction.

"fixed" (the original behavior): always trade the same unit count, no
matter how volatile the instrument currently is -- a quiet stretch and a
wild stretch get treated identically.

"volatility" sizing: risk a fixed percentage of account balance per trade,
with size scaled inversely to recent volatility (Average True Range) --
calmer markets get a bigger position, choppier ones get a smaller one, so
the *dollar risk* per trade stays roughly constant instead of the *unit
count*. This is a standard retail risk-management approach, not something
novel, and it only sizes the next trade -- it doesn't place a real stop
order, so a big enough single move can still lose more than the risk
budget.

Sizing bounds (min_notional / max_notional_pct) are expressed in account-
currency VALUE, not raw unit counts -- unit count alone means wildly
different things across assets (1 unit of EUR_USD is ~$1, 1 unit of
BTC-USD is ~$78,000+), so a raw "min 100 units" floor that's a sane $108
position on EUR_USD becomes an ~800x-leveraged $7.8M position on BTC-USD.
Bounding by notional value scales correctly across any instrument.

Sizes are fractional (e.g. 0.06 BTC), not whole-unit-only -- a whole-unit
floor is harmless for forex (1 unit of EUR is ~$1) but would make sane
risk-sized positions on high-priced assets impossible at retail account
sizes (a risk-appropriate BTC-USD position is routinely well under 1 BTC).
The "simulated" broker supports fractions natively; the real OANDA broker
rounds to whole units at the point of ordering (see live/oanda_client.py)
since OANDA forex/CFD instruments don't accept fractional units -- not a
practical issue there since OANDA doesn't offer crypto anyway.

Simplification worth knowing: this treats 1 unit of the base currency as
worth 1 unit of account currency of risk (correct for pairs like EUR_USD
or BTC_USD where the account is denominated in the quote currency, USD;
it's an approximation for other pairs). Not modeled: spread cost, margin
requirements, or correlation across simultaneously open instruments.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class PositionSizingConfig:
    mode: str = "fixed"  # "fixed" or "volatility"
    fixed_units: int = 1000
    risk_pct: float = 0.01
    atr_period: int = 14
    atr_multiplier: float = 1.5
    min_notional: float = 50.0       # smallest position value worth opening, in account currency
    max_notional_pct: float = 0.5    # largest position value, as a fraction of balance (0.5 = no leverage beyond half the account)


def average_true_range(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(period).mean()


def volatility_based_units(
    balance: float,
    price: float,
    atr: float,
    risk_pct: float = 0.01,
    atr_multiplier: float = 1.5,
    min_notional: float = 50.0,
    max_notional_pct: float = 0.5,
) -> float:
    """Units sized so that a move of atr_multiplier * ATR against the
    position would cost roughly risk_pct of balance, bounded to a position
    worth between min_notional and max_notional_pct * balance. Fractional --
    see module docstring for why a whole-unit floor isn't safe here."""
    if price is None or price <= 0 or balance <= 0:
        return 0.0
    min_units = min_notional / price
    max_units = (balance * max_notional_pct) / price

    if atr is None or atr <= 0 or pd.isna(atr):
        return min_units

    risk_amount = balance * risk_pct
    stop_distance = atr * atr_multiplier
    units = risk_amount / stop_distance
    return max(min_units, min(units, max_units))


def compute_units(df: pd.DataFrame, balance: float, cfg: PositionSizingConfig) -> float:
    if cfg.mode == "fixed":
        return cfg.fixed_units
    if cfg.mode != "volatility":
        raise ValueError(f"Unknown position sizing mode '{cfg.mode}', expected 'fixed' or 'volatility'")

    atr_series = average_true_range(df, period=cfg.atr_period)
    current_atr = float(atr_series.iloc[-1]) if len(atr_series) else None
    current_price = float(df["close"].iloc[-1])
    return volatility_based_units(
        balance, current_price, current_atr, risk_pct=cfg.risk_pct, atr_multiplier=cfg.atr_multiplier,
        min_notional=cfg.min_notional, max_notional_pct=cfg.max_notional_pct,
    )
