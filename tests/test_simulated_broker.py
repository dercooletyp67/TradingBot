import pandas as pd
import pytest

from live.simulated_broker import SimulatedBroker


@pytest.fixture
def mock_price(monkeypatch):
    """Lets a test control what price the broker sees, without touching
    the network. price_box[0] is read fresh on every call, so a test can
    mutate it mid-scenario to simulate the market moving."""
    price_box = [1.1000]

    def fake_fetch(instrument, granularity, count):
        index = pd.date_range("2024-01-01", periods=count, freq="h")
        price = price_box[0]
        return pd.DataFrame(
            {"open": price, "high": price, "low": price, "close": price}, index=index
        )

    monkeypatch.setattr("live.simulated_broker.fetch_yfinance_candles", fake_fetch)
    return price_box


def test_opening_a_long_position_sets_entry_price_above_market(temp_db, mock_price):
    mock_price[0] = 1.1000
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=2.0)

    resp = broker.place_market_order("EUR_USD", 1000)

    fill_price = resp["orderFillTransaction"]["price"]
    assert fill_price > 1.1000  # buys pay the spread, fill above mid
    assert broker.get_open_units("EUR_USD") == 1000
    assert resp["orderFillTransaction"]["pl"] == 0.0  # opening has no realized pnl


def test_closing_a_profitable_long_realizes_gain(temp_db, mock_price):
    mock_price[0] = 1.1000
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    broker.place_market_order("EUR_USD", 1000)

    mock_price[0] = 1.2000  # price rallies
    close_resp = broker.place_market_order("EUR_USD", -1000)

    assert close_resp["orderFillTransaction"]["pl"] == pytest.approx(100.0, abs=0.01)
    assert broker.get_open_units("EUR_USD") == 0
    summary = broker.get_account_summary()
    assert summary["balance"] == pytest.approx(10_100.0, abs=0.01)


def test_closing_a_losing_short_realizes_loss(temp_db, mock_price):
    mock_price[0] = 1.1000
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    broker.place_market_order("EUR_USD", -1000)  # open short

    mock_price[0] = 1.2000  # price rises against the short
    close_resp = broker.place_market_order("EUR_USD", 1000)

    assert close_resp["orderFillTransaction"]["pl"] == pytest.approx(-100.0, abs=0.01)
    summary = broker.get_account_summary()
    assert summary["balance"] == pytest.approx(9_900.0, abs=0.01)


def test_adding_to_a_position_blends_entry_price(temp_db, mock_price):
    mock_price[0] = 1.0000
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    broker.place_market_order("EUR_USD", 1000)  # entry at 1.0000

    mock_price[0] = 1.1000
    broker.place_market_order("EUR_USD", 1000)  # add another 1000 at 1.1000

    state_units = broker.get_open_units("EUR_USD")
    assert state_units == 2000
    # blended entry should be the average: (1.0000*1000 + 1.1000*1000) / 2000
    from storage.db import get_sim_state
    assert get_sim_state()["sim_entry_price"] == pytest.approx(1.0500)


def test_flipping_through_zero_realizes_pnl_on_closed_portion_and_reopens(temp_db, mock_price):
    mock_price[0] = 1.0000
    broker = SimulatedBroker("EUR_USD", "H1", starting_balance=10_000.0, spread_bps=0.0)
    broker.place_market_order("EUR_USD", 1000)  # long 1000 @ 1.0000

    mock_price[0] = 1.1000
    flip_resp = broker.place_market_order("EUR_USD", -2000)  # close 1000, open short 1000

    assert flip_resp["orderFillTransaction"]["pl"] == pytest.approx(100.0, abs=0.01)  # closed leg profit
    assert broker.get_open_units("EUR_USD") == -1000

    from storage.db import get_sim_state
    assert get_sim_state()["sim_entry_price"] == pytest.approx(1.1000)  # new short opened at flip price


def test_starting_balance_only_applied_once(temp_db, mock_price):
    broker1 = SimulatedBroker("EUR_USD", "H1", starting_balance=5_000.0)
    assert broker1.get_account_summary()["balance"] == 5_000.0

    # a second broker instance (e.g. next tick's fresh process) should NOT
    # reset the balance back to the starting value -- it must resume.
    broker1.place_market_order("EUR_USD", 1000)
    broker2 = SimulatedBroker("EUR_USD", "H1", starting_balance=5_000.0)
    assert broker2.get_open_units("EUR_USD") == 1000
