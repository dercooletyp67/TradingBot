from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import BacktestResult


@dataclass
class Metrics:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: float
    profit_factor: float

    def as_dict(self) -> dict:
        return self.__dict__


def compute_metrics(result: BacktestResult, bars_per_year: float) -> Metrics:
    equity = result.equity_curve
    returns = result.returns
    trades = result.trades

    total_return = equity.iloc[-1] / equity.iloc[0] - 1 if len(equity) else 0.0

    n_bars = len(equity)
    years = n_bars / bars_per_year if bars_per_year else 0
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else 0.0

    ret_std = returns.std()
    sharpe = (returns.mean() / ret_std) * np.sqrt(bars_per_year) if ret_std and ret_std > 0 else 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    max_drawdown = drawdown.min() if len(drawdown) else 0.0

    if len(trades):
        wins = trades[trades["return_pct"] > 0]
        losses = trades[trades["return_pct"] <= 0]
        win_rate = len(wins) / len(trades)
        gross_profit = wins["return_pct"].sum()
        gross_loss = -losses["return_pct"].sum()
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    else:
        win_rate = 0.0
        profit_factor = 0.0

    return Metrics(
        total_return_pct=total_return * 100,
        cagr_pct=cagr * 100,
        sharpe=sharpe,
        max_drawdown_pct=max_drawdown * 100,
        num_trades=len(trades),
        win_rate_pct=win_rate * 100,
        profit_factor=profit_factor,
    )


GRANULARITY_BARS_PER_YEAR = {
    "M1": 365 * 24 * 60,
    "M5": 365 * 24 * 12,
    "M15": 365 * 24 * 4,
    "M30": 365 * 24 * 2,
    "H1": 365 * 24,
    "H4": 365 * 6,
    "D": 252,
}
