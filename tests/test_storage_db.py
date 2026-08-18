from storage.db import (
    get_equity_snapshots,
    get_retune_events,
    get_sim_state,
    get_trades,
    record_equity_snapshot,
    record_retune_event,
    record_trade,
    reset_sim_state,
    set_sim_state,
)


def test_fresh_db_has_zero_sim_balance_until_reset(temp_db):
    # regression test: SimulatedBroker relies on a fresh DB starting at
    # balance <= 0 to know it should apply a custom starting balance --
    # if the schema default were ever a positive number again, that logic
    # would silently break (see live/simulated_broker.py).
    assert get_sim_state()["sim_balance"] <= 0


def test_reset_sim_state_applies_custom_starting_balance(temp_db):
    reset_sim_state(starting_balance=5_000.0)
    state = get_sim_state()
    assert state["sim_balance"] == 5_000.0
    assert state["sim_position_units"] == 0
    assert state["sim_entry_price"] == 0


def test_sim_state_round_trip(temp_db):
    set_sim_state(balance=9_876.5, position_units=-500, entry_price=1.2345)
    state = get_sim_state()
    assert state["sim_balance"] == 9_876.5
    assert state["sim_position_units"] == -500
    assert state["sim_entry_price"] == 1.2345


def test_trades_recorded_and_read_back_newest_first(temp_db):
    record_trade("sma_cross", "EUR_USD", "buy", 1000, 1.1000, pnl=0.0)
    record_trade("sma_cross", "EUR_USD", "sell", 1000, 1.1050, pnl=5.0)

    trades = get_trades()
    assert len(trades) == 2
    assert trades[0]["side"] == "sell"  # newest first
    assert trades[1]["side"] == "buy"


def test_equity_snapshots_read_back_oldest_first(temp_db):
    record_equity_snapshot("sma_cross", "EUR_USD", balance=10_000.0)
    record_equity_snapshot("sma_cross", "EUR_USD", balance=10_050.0)

    snapshots = get_equity_snapshots()
    assert len(snapshots) == 2
    assert snapshots[0]["balance"] == 10_000.0  # oldest first, for charting
    assert snapshots[1]["balance"] == 10_050.0


def test_retune_events_recorded_and_read_back(temp_db):
    record_retune_event(
        "sma_cross", '{"fast": 10, "slow": 50}',
        "rsi_reversion", '{"period": 21}',
        mean_test_sharpe=1.5, overfit_gap=0.3, changed=True,
    )

    events = get_retune_events()
    assert len(events) == 1
    assert events[0]["new_strategy"] == "rsi_reversion"
    assert events[0]["changed"] == 1
