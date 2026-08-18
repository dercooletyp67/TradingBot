import pandas as pd
import pytest

from backtest.engine import BacktestResult
from backtest.metrics import compute_metrics


def _result(equity_values, trades=None):
    index = pd.date_range("2024-01-01", periods=len(equity_values), freq="h")
    equity = pd.Series(equity_values, index=index)
    returns = equity.pct_change().fillna(0)
    position = pd.Series(0, index=index)
    return BacktestResult(
        equity_curve=equity, returns=returns, position=position,
        trades=pd.DataFrame(trades or []),
    )


def test_total_return_and_drawdown():
    # 1000 -> 1200 (+20%) -> 900 (peak-to-trough from 1200 is -25%) -> 1100
    result = _result([1000, 1200, 900, 1100])

    metrics = compute_metrics(result, bars_per_year=24 * 365)

    assert metrics.total_return_pct == pytest.approx(10.0)
    assert metrics.max_drawdown_pct == pytest.approx(-25.0)


def test_win_rate_and_profit_factor_from_trades():
    trades = [
        {"return_pct": 0.05},
        {"return_pct": 0.03},
        {"return_pct": -0.02},
    ]
    result = _result([1000, 1050, 1080, 1060], trades=trades)

    metrics = compute_metrics(result, bars_per_year=24 * 365)

    assert metrics.num_trades == 3
    assert metrics.win_rate_pct == pytest.approx(200 / 3)  # 2 of 3 trades won
    assert metrics.profit_factor == pytest.approx(0.08 / 0.02)


def test_no_trades_gives_zero_win_rate_not_a_crash():
    result = _result([1000, 1000, 1000])

    metrics = compute_metrics(result, bars_per_year=252)

    assert metrics.num_trades == 0
    assert metrics.win_rate_pct == 0.0
    assert metrics.profit_factor == 0.0


def test_flat_equity_gives_zero_sharpe_not_nan_or_inf():
    result = _result([1000, 1000, 1000, 1000])

    metrics = compute_metrics(result, bars_per_year=252)

    assert metrics.sharpe == 0.0
