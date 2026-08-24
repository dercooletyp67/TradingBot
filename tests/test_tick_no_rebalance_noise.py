"""Regression test for the rebalancing-noise bug: volatility-based position
sizing used to recompute the target size on every tick, so a same-direction
signal could still trigger a tiny trade just because ATR/balance drifted.
_tick() should only resize on an actual direction change."""
import pandas as pd
import pytest

from live.paper_trader import _tick
from live.position_sizing import PositionSizingConfig
from live.simulated_broker import SimulatedBroker
from storage.db import get_trades


class _ConstantSignalStrategy:
    """A fake strategy whose signal never changes, so any trade that
    happens after the first tick must be spurious rebalancing noise."""

    def __init__(self, signal_value: int):
        self.signal_value = signal_value

    def generate_signals(self, df, **params):
        return pd.Series(self.signal_value, index=df.index)


@pytest.fixture
def mock_price_with_drifting_volatility(monkeypatch):
    """Each call returns slightly different high/low spread (and thus a
    different ATR) so a naive implementation would keep resizing."""
    call_count = [0]

    def fake_fetch(instrument, granularity, count):
        call_count[0] += 1
        spread = 0.0010 + call_count[0] * 0.0002  # ATR drifts wider each call
        price = 1.1000
        index = pd.date_range("2024-01-01", periods=count, freq="h")
        return pd.DataFrame(
            {
                "open": price,
                "high": price + spread / 2,
                "low": price - spread / 2,
                "close": price,
            },
            index=index,
        )

    monkeypatch.setattr("live.simulated_broker.fetch_yfinance_candles", fake_fetch)
    return call_count


def test_same_direction_signal_does_not_retrigger_a_trade(temp_db, mock_price_with_drifting_volatility):
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    strategy = _ConstantSignalStrategy(signal_value=1)  # always wants long
    cfg = PositionSizingConfig(mode="volatility", risk_pct=0.01, atr_multiplier=1.5)

    _tick(broker, strategy, "test_strategy", {}, "EUR_USD", "H1", cfg)
    assert len(get_trades()) == 1  # the initial entry

    # ATR (and thus the "ideal" size) keeps drifting on every subsequent
    # tick, but the signal never changed direction -- must not re-trade.
    for _ in range(5):
        _tick(broker, strategy, "test_strategy", {}, "EUR_USD", "H1", cfg)

    assert len(get_trades()) == 1  # still just the one entry, no rebalancing noise


def test_direction_change_still_trades_correctly(temp_db, mock_price_with_drifting_volatility):
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    cfg = PositionSizingConfig(mode="volatility", risk_pct=0.01, atr_multiplier=1.5)

    long_strategy = _ConstantSignalStrategy(signal_value=1)
    _tick(broker, long_strategy, "test_strategy", {}, "EUR_USD", "H1", cfg)
    assert broker.get_open_units("EUR_USD") > 0

    flat_strategy = _ConstantSignalStrategy(signal_value=0)
    _tick(broker, flat_strategy, "test_strategy", {}, "EUR_USD", "H1", cfg)
    assert broker.get_open_units("EUR_USD") == 0

    short_strategy = _ConstantSignalStrategy(signal_value=-1)
    _tick(broker, short_strategy, "test_strategy", {}, "EUR_USD", "H1", cfg)
    assert broker.get_open_units("EUR_USD") < 0

    assert len(get_trades()) == 3  # one trade per genuine direction change
