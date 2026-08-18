"""Vectorized single-instrument backtester.

Signals are assumed decided using information available at the close of bar
t; the resulting position is applied to the bar-over-bar return from t to
t+1 (i.e. we shift the signal forward by one bar) so there's no lookahead
bias. A cost is charged in price terms whenever the position changes, to
approximate spread + slippage.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    position: pd.Series
    trades: pd.DataFrame


def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    initial_capital: float = 10_000.0,
    cost_bps: float = 2.0,
    extract_trades: bool = True,
) -> BacktestResult:
    """
    df: OHLC data with a 'close' column, DatetimeIndex.
    signal: position per bar, -1/0/1, same index as df.
    cost_bps: round-trip-ish cost in basis points of price, charged whenever
              position size changes (approximates spread + slippage).
    extract_trades: set False during large parameter sweeps to skip the
              (relatively slow) per-bar trade reconstruction loop -- only the
              equity curve / returns are needed to rank candidates.
    """
    signal = signal.reindex(df.index).fillna(0)
    position = signal.shift(1).fillna(0)

    price_returns = df["close"].pct_change().fillna(0)
    gross_returns = position * price_returns

    position_change = position.diff().abs().fillna(position.abs())
    cost = position_change * (cost_bps / 10_000.0)
    net_returns = gross_returns - cost

    equity_curve = initial_capital * (1 + net_returns).cumprod()

    trades = _extract_trades(df, position, initial_capital) if extract_trades else pd.DataFrame()

    return BacktestResult(
        equity_curve=equity_curve, returns=net_returns, position=position, trades=trades
    )


def _extract_trades(df: pd.DataFrame, position: pd.Series, initial_capital: float) -> pd.DataFrame:
    """Reconstruct discrete trades (entry -> exit) from the position series."""
    trades = []
    entry_idx = None
    entry_pos = 0

    for i, (ts, pos) in enumerate(position.items()):
        if pos != entry_pos:
            if entry_pos != 0 and entry_idx is not None:
                entry_price = df["close"].iloc[entry_idx]
                exit_price = df["close"].iloc[i]
                pnl_pct = entry_pos * (exit_price - entry_price) / entry_price
                trades.append(
                    {
                        "entry_time": df.index[entry_idx],
                        "exit_time": ts,
                        "side": "long" if entry_pos == 1 else "short",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "return_pct": pnl_pct,
                    }
                )
            entry_idx = i if pos != 0 else None
            entry_pos = pos

    return pd.DataFrame(trades)
