"""Integration test: the kill switch actually flattens the position and
halts trading within _tick(), not just in isolation (see test_kill_switch.py
for the pure decision-function tests)."""
import pandas as pd
import pytest

from live.paper_trader import _tick
from live.position_sizing import PositionSizingConfig
from live.simulated_broker import SimulatedBroker
from storage.db import get_bot_status, get_trades, is_trading_halted


class _ConstantSignalStrategy:
    def __init__(self, signal_value: int):
        self.signal_value = signal_value

    def generate_signals(self, df, **params):
        return pd.Series(self.signal_value, index=df.index)


@pytest.fixture
def mock_price(monkeypatch):
    price_box = [1.1000]

    def fake_fetch(instrument, granularity, count):
        index = pd.date_range("2024-01-01", periods=count, freq="h")
        price = price_box[0]
        return pd.DataFrame(
            {"open": price, "high": price, "low": price, "close": price}, index=index
        )

    monkeypatch.setattr("live.simulated_broker.fetch_yfinance_candles", fake_fetch)
    return price_box


def test_kill_switch_flattens_and_halts_on_large_drawdown(temp_db, mock_price):
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    long_strategy = _ConstantSignalStrategy(signal_value=1)
    # 10,000 units @ ~1.10 is ~$11,000 notional against a $10,000 account --
    # large enough that a real price move produces a real ACCOUNT drawdown,
    # not just a small dent (1000 units, ~$1,100 notional, physically can't
    # produce a 10%-of-account loss no matter how far the price falls).
    cfg = PositionSizingConfig(mode="fixed", fixed_units=10_000)

    mock_price[0] = 1.1000
    _tick(broker, long_strategy, "test_strategy", {}, "EUR_USD", "H1", cfg, max_drawdown_pct=10.0)
    assert broker.get_open_units("EUR_USD") == 10_000
    assert is_trading_halted() is False

    # price drops ~14% -- unrealized loss is ~15% of total account equity
    mock_price[0] = 0.9500
    _tick(broker, long_strategy, "test_strategy", {}, "EUR_USD", "H1", cfg, max_drawdown_pct=10.0)

    assert is_trading_halted() is True
    assert broker.get_open_units("EUR_USD") == 0  # position flattened
    status = get_bot_status()
    assert status["halted_reason"] is not None

    trades = get_trades()
    assert len(trades) == 2  # the entry, then the kill-switch flatten
    assert trades[0]["side"] == "sell"  # most recent = the flatten (closing a long)


def test_halted_tick_skips_trading_entirely(temp_db, mock_price):
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    strategy = _ConstantSignalStrategy(signal_value=1)
    cfg = PositionSizingConfig(mode="fixed", fixed_units=10_000)

    mock_price[0] = 1.1000
    _tick(broker, strategy, "test_strategy", {}, "EUR_USD", "H1", cfg, max_drawdown_pct=10.0)
    mock_price[0] = 0.9500
    _tick(broker, strategy, "test_strategy", {}, "EUR_USD", "H1", cfg, max_drawdown_pct=10.0)
    assert is_trading_halted() is True
    trades_after_halt = len(get_trades())

    # price recovers, strategy still wants long -- but halted, must not re-enter
    mock_price[0] = 1.2000
    _tick(broker, strategy, "test_strategy", {}, "EUR_USD", "H1", cfg, max_drawdown_pct=10.0)

    assert broker.get_open_units("EUR_USD") == 0
    assert len(get_trades()) == trades_after_halt  # no new trades while halted


def test_no_kill_switch_when_max_drawdown_pct_is_none(temp_db, mock_price):
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    strategy = _ConstantSignalStrategy(signal_value=1)
    cfg = PositionSizingConfig(mode="fixed", fixed_units=1000)

    mock_price[0] = 1.1000
    _tick(broker, strategy, "test_strategy", {}, "EUR_USD", "H1", cfg, max_drawdown_pct=None)
    mock_price[0] = 0.5000  # catastrophic drop
    _tick(broker, strategy, "test_strategy", {}, "EUR_USD", "H1", cfg, max_drawdown_pct=None)

    assert is_trading_halted() is False
    assert broker.get_open_units("EUR_USD") == 1000  # still holding, kill switch is off
