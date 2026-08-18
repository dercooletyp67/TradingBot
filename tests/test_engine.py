import pandas as pd
import pytest

from backtest.engine import run_backtest


def _make_df(closes):
    index = pd.date_range("2024-01-01", periods=len(closes), freq="h")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes}, index=index
    )


def test_signal_applies_to_next_bar_not_same_bar():
    # Price jumps 100 -> 110 on bar 1. A signal that only turns on AT bar 1
    # (after seeing the jump) must not capture that bar's return -- no
    # lookahead. It should only start earning returns from bar 2 onward.
    df = _make_df([100, 110, 110, 110])
    signal = pd.Series([0, 1, 1, 1], index=df.index)

    result = run_backtest(df, signal, initial_capital=1000, cost_bps=0)

    assert result.returns.iloc[1] == 0  # the 100->110 jump itself is not captured
    assert result.equity_curve.iloc[1] == 1000  # unchanged on the jump bar


def test_flat_signal_never_trades():
    df = _make_df([100, 105, 95, 110])
    signal = pd.Series(0, index=df.index)

    result = run_backtest(df, signal, initial_capital=1000, cost_bps=2.0)

    assert (result.returns == 0).all()
    assert (result.equity_curve == 1000).all()
    assert result.trades.empty


def test_cost_charged_only_when_position_changes():
    df = _make_df([100, 100, 100, 100, 100])
    signal = pd.Series([1, 1, 1, 0, 0], index=df.index)

    result = run_backtest(df, signal, initial_capital=1000, cost_bps=10.0)  # 10bps = 0.1%

    # position becomes 1 after bar 0->1 shift; changes happen entering (bar1)
    # and exiting (bar4, when position drops from 1 to 0).
    position_changes = result.position.diff().abs().fillna(result.position.abs())
    non_zero_change_bars = position_changes[position_changes != 0]
    assert len(non_zero_change_bars) == 2  # one entry, one exit
    # each cost hit should be exactly 10bps since position size is always 1
    for cost_bar_return in result.returns[position_changes != 0]:
        assert cost_bar_return == -0.001


def test_long_position_captures_full_upside_minus_cost():
    df = _make_df([100, 100, 200])  # bar1->bar2 return is +100%
    signal = pd.Series([1, 1, 1], index=df.index)

    result = run_backtest(df, signal, initial_capital=1000, cost_bps=0)

    # position already 1 entering bar2 (no change), so full return captured
    assert result.returns.iloc[2] == 1.0
    assert result.equity_curve.iloc[2] == 2000


def test_short_position_profits_from_price_drop():
    df = _make_df([100, 100, 50])  # bar1->bar2 return is -50%
    signal = pd.Series([-1, -1, -1], index=df.index)

    result = run_backtest(df, signal, initial_capital=1000, cost_bps=0)

    assert result.returns.iloc[2] == 0.5
    assert result.equity_curve.iloc[2] == 1500


def test_extract_trades_reconstructs_entry_and_exit():
    df = _make_df([100, 100, 100, 120, 120])
    signal = pd.Series([1, 1, 1, 0, 0], index=df.index)

    result = run_backtest(df, signal, initial_capital=1000, cost_bps=0)

    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["side"] == "long"
    assert trade["entry_price"] == 100
    assert trade["exit_price"] == 120
    assert trade["return_pct"] == pytest.approx(0.2)
