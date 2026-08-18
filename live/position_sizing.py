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

Simplification worth knowing: this treats 1 unit of the base currency as
worth 1 unit of account currency of risk (correct for pairs like EUR_USD
where the account is denominated in the quote currency, USD; it's an
approximation for other pairs). Not modeled: spread cost, margin
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
    min_units: int = 100
    max_units: int = 100_000


def average_true_range(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(period).mean()


def volatility_based_units(
    balance: float,
    atr: float,
    risk_pct: float = 0.01,
    atr_multiplier: float = 1.5,
    min_units: int = 100,
    max_units: int = 100_000,
) -> int:
    """Units sized so that a move of atr_multiplier * ATR against the
    position would cost roughly risk_pct of balance."""
    if atr is None or atr <= 0 or pd.isna(atr) or balance <= 0:
        return min_units
    risk_amount = balance * risk_pct
    stop_distance = atr * atr_multiplier
    units = int(risk_amount / stop_distance)
    return max(min_units, min(units, max_units))


def compute_units(df: pd.DataFrame, balance: float, cfg: PositionSizingConfig) -> int:
    if cfg.mode == "fixed":
        return cfg.fixed_units
    if cfg.mode != "volatility":
        raise ValueError(f"Unknown position sizing mode '{cfg.mode}', expected 'fixed' or 'volatility'")

    atr_series = average_true_range(df, period=cfg.atr_period)
    current_atr = float(atr_series.iloc[-1]) if len(atr_series) else None
    return volatility_based_units(
        balance, current_atr, risk_pct=cfg.risk_pct, atr_multiplier=cfg.atr_multiplier,
        min_units=cfg.min_units, max_units=cfg.max_units,
    )
