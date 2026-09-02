"""Runs a strategy against a "paper" trading backend, either as a
continuous polling loop (local/desktop use) or as a single stateless tick
(cron-driven, e.g. GitHub Actions -- see run_paper_trader_once).

Each cycle: pull recent candles, compute the strategy's desired position,
compare it to the currently open position, and place a market order for the
difference. All fills and account snapshots are logged to SQLite so a
dashboard can show them.

Two backends:
  - "simulated" (default): no broker account at all. Price data comes from
    Yahoo Finance and the fake balance/position are tracked locally in
    SQLite. Zero signup required.
  - "oanda": routes through a real OANDA demo/practice account (requires
    OANDA_API_KEY/OANDA_ACCOUNT_ID in .env). Still fake money -- OANDA's own
    demo account -- but real broker-side order matching.

Whatever strategy/params ends up active (whether the CLI-provided seed or a
later auto-retune pick) is persisted in bot_status and resumed from there on
every start -- restarting the process (a reboot, a fresh cron invocation)
does not throw away what a previous run's auto-retune had settled on.

If --max-drawdown-pct is set, a kill switch flattens the position and halts
all trading once equity falls that far below its all-time peak, until
manually cleared with --resume-trading (see live/kill_switch.py).
"""
from __future__ import annotations

import datetime as dt
import json
import time

from live.kill_switch import check_drawdown
from live.learn_log import append_history, write_current_strategy
from live.notify import notify_kill_switch, notify_retune, notify_trade
from live.position_sizing import PositionSizingConfig, compute_units
from storage.db import (
    get_bot_status,
    get_last_retune_at,
    halt_trading,
    heartbeat,
    init_db,
    is_trading_halted,
    record_equity_snapshot,
    record_retune_event,
    record_trade,
    set_bot_status,
    set_last_retune_at,
)
from strategies.base import get_strategy

# Enough bars for the slowest indicator lookback any bundled strategy uses (SMA 200).
CANDLE_LOOKBACK = 500


def _make_client(broker: str, instrument: str, granularity: str, starting_balance: float):
    if broker == "simulated":
        from live.simulated_broker import SimulatedBroker

        return SimulatedBroker(instrument, granularity, starting_balance=starting_balance)
    elif broker == "oanda":
        from live.oanda_client import OandaClient

        return OandaClient()
    raise ValueError(f"Unknown broker '{broker}', expected 'simulated' or 'oanda'")


def _resolve_seed(strategy_name: str, params: dict) -> tuple[str, dict, bool]:
    """Resume from whatever's already active in bot_status; only fall back
    to the CLI-provided seed on a genuinely first run. Returns
    (strategy_name, params, is_fresh_seed)."""
    existing = get_bot_status()
    if existing.get("strategy"):
        return existing["strategy"], json.loads(existing["params_json"]), False
    return strategy_name, dict(params), True


def _retune_due(auto_retune_hours: float | None) -> bool:
    if not auto_retune_hours:
        return False
    last = get_last_retune_at()
    if last is None:
        return False
    elapsed = (dt.datetime.utcnow() - dt.datetime.fromisoformat(last)).total_seconds()
    return elapsed >= auto_retune_hours * 3600


def _fill_and_record(client, instrument, active_strategy_name, units_delta) -> None:
    resp = client.place_market_order(instrument, units_delta)
    fill = resp.get("orderFillTransaction")
    if fill:
        price = float(fill["price"])
        side = "buy" if units_delta > 0 else "sell"
        pnl = float(fill.get("pl", 0.0))
        record_trade(active_strategy_name, instrument, side, abs(units_delta), price, pnl, fill.get("id"))
        print(f"Filled {side} {abs(units_delta)} units {instrument} @ {price}")
        notify_trade(active_strategy_name, instrument, side, abs(units_delta), price, pnl)
    else:
        print(f"Order not filled: {resp}")


def _tick(
    client, strategy, active_strategy_name, active_params, instrument, granularity,
    position_sizing: PositionSizingConfig, max_drawdown_pct: float | None = None,
) -> None:
    if is_trading_halted():
        account = client.get_account_summary()
        record_equity_snapshot(
            active_strategy_name, instrument,
            balance=float(account["balance"]), unrealized_pnl=float(account["unrealizedPL"]),
        )
        heartbeat()
        print("Trading halted (kill switch tripped) -- skipping this tick. Run with --resume-trading to clear it.")
        return

    df = client.get_recent_candles(instrument, granularity, count=CANDLE_LOOKBACK)
    if len(df) < 50:
        print("Not enough candle history yet, waiting...")
        return

    signal = strategy.generate_signals(df, **active_params)
    desired_signal = int(signal.iloc[-1])

    current_units = client.get_open_units(instrument)
    current_direction = 0 if current_units == 0 else (1 if current_units > 0 else -1)

    delta = 0
    if desired_signal != current_direction:
        # Only a real direction change (flat->open, or a flip) re-sizes the
        # position. Recomputing size every tick from the latest ATR/balance
        # -- even while the strategy's direction hasn't moved at all -- was
        # producing a stream of tiny rebalancing trades with pnl=0 that
        # inflated the trade count and skewed win-rate stats.
        account = client.get_account_summary()
        balance = float(account["balance"])
        units = compute_units(df, balance, position_sizing)
        desired_units = desired_signal * units
        delta = desired_units - current_units

    if delta != 0:
        _fill_and_record(client, instrument, active_strategy_name, delta)

    account = client.get_account_summary()
    balance = float(account["balance"])
    unrealized = float(account["unrealizedPL"])
    record_equity_snapshot(active_strategy_name, instrument, balance=balance, unrealized_pnl=unrealized)
    heartbeat()

    should_halt, drawdown_pct = check_drawdown(balance + unrealized, max_drawdown_pct)
    if should_halt:
        open_units = client.get_open_units(instrument)
        if open_units != 0:
            _fill_and_record(client, instrument, active_strategy_name, -open_units)
        reason = f"Drawdown {drawdown_pct:.1f}% exceeded -{max_drawdown_pct:.1f}% limit"
        halt_trading(reason)
        print(f"*** TRADING HALTED: {reason} ***")
        notify_kill_switch(drawdown_pct, max_drawdown_pct)


def run_paper_trader(
    strategy_name: str,
    params: dict,
    instrument: str,
    granularity: str,
    position_sizing: PositionSizingConfig | None = None,
    poll_seconds: int = 60,
    broker: str = "simulated",
    starting_balance: float = 10_000.0,
    auto_retune_hours: float | None = None,
    retune_strategies: list[str] | None = None,
    retune_folds: int = 4,
    retune_min_oos_sharpe: float = 0.0,
    retune_max_overfit_gap: float = 1.5,
    retune_search_mode: str = "grid",
    retune_max_combos: int | None = None,
    retune_require_clear_noise_bar: bool = True,
    max_drawdown_pct: float | None = None,
) -> None:
    """Continuous polling loop: stays alive, sleeps between checks. For
    local/desktop use (see scripts/start_tradingbot.ps1)."""
    position_sizing = position_sizing or PositionSizingConfig()
    init_db()

    active_strategy_name, active_params, is_fresh = _resolve_seed(strategy_name, params)
    strategy = get_strategy(active_strategy_name)
    client = _make_client(broker, instrument, granularity, starting_balance)

    if is_fresh:
        write_current_strategy(active_strategy_name, active_params, source="seed")
    if get_last_retune_at() is None:
        set_last_retune_at(dt.datetime.utcnow().isoformat())

    set_bot_status(active_strategy_name, instrument, json.dumps(active_params), running=True)
    print(
        f"Paper trading {active_strategy_name}{active_params} on {instrument} ({granularity}) via "
        f"'{broker}' broker, polling every {poll_seconds}s."
    )
    if auto_retune_hours:
        print(f"Auto re-tune enabled: re-searching every {auto_retune_hours}h, guardrails "
              f"min_oos_sharpe={retune_min_oos_sharpe}, max_overfit_gap={retune_max_overfit_gap}, "
              f"require_clear_noise_bar={retune_require_clear_noise_bar}.")
    if max_drawdown_pct:
        print(f"Kill switch enabled: halts trading if equity drops {max_drawdown_pct}% below its peak.")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            if _retune_due(auto_retune_hours):
                new_name, new_params = _run_retune_cycle(
                    active_strategy_name, active_params, instrument, granularity,
                    retune_strategies, retune_folds, retune_min_oos_sharpe,
                    retune_max_overfit_gap, retune_search_mode, retune_max_combos,
                    retune_require_clear_noise_bar,
                )
                if new_name != active_strategy_name or new_params != active_params:
                    active_strategy_name, active_params = new_name, new_params
                    strategy = get_strategy(active_strategy_name)
                    set_bot_status(active_strategy_name, instrument, json.dumps(active_params), running=True)

            _tick(
                client, strategy, active_strategy_name, active_params, instrument, granularity,
                position_sizing, max_drawdown_pct,
            )
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("Stopping paper trader.")
    finally:
        set_bot_status(active_strategy_name, instrument, json.dumps(active_params), running=False)


def run_paper_trader_once(
    strategy_name: str,
    params: dict,
    instrument: str,
    granularity: str,
    position_sizing: PositionSizingConfig | None = None,
    broker: str = "simulated",
    starting_balance: float = 10_000.0,
    auto_retune_hours: float | None = None,
    retune_strategies: list[str] | None = None,
    retune_folds: int = 4,
    retune_min_oos_sharpe: float = 0.0,
    retune_max_overfit_gap: float = 1.5,
    retune_search_mode: str = "grid",
    retune_max_combos: int | None = None,
    retune_require_clear_noise_bar: bool = True,
    max_drawdown_pct: float | None = None,
) -> None:
    """A single check-and-maybe-trade cycle, then exit. For stateless
    cron-driven runs (e.g. GitHub Actions), where each invocation is a fresh
    process with no memory of previous ones -- all state that needs to
    survive between ticks lives in SQLite, not in this process."""
    position_sizing = position_sizing or PositionSizingConfig()
    init_db()

    active_strategy_name, active_params, is_fresh = _resolve_seed(strategy_name, params)
    strategy = get_strategy(active_strategy_name)
    client = _make_client(broker, instrument, granularity, starting_balance)

    if is_fresh:
        write_current_strategy(active_strategy_name, active_params, source="seed")
        set_last_retune_at(dt.datetime.utcnow().isoformat())
    elif _retune_due(auto_retune_hours):
        new_name, new_params = _run_retune_cycle(
            active_strategy_name, active_params, instrument, granularity,
            retune_strategies, retune_folds, retune_min_oos_sharpe,
            retune_max_overfit_gap, retune_search_mode, retune_max_combos,
            retune_require_clear_noise_bar,
        )
        active_strategy_name, active_params = new_name, new_params
        strategy = get_strategy(active_strategy_name)

    print(f"Tick: {active_strategy_name}{active_params} on {instrument} ({granularity}) via '{broker}' broker.")
    _tick(
        client, strategy, active_strategy_name, active_params, instrument, granularity,
        position_sizing, max_drawdown_pct,
    )
    set_bot_status(active_strategy_name, instrument, json.dumps(active_params), running=True)


def _run_retune_cycle(
    current_strategy_name, current_params, instrument, granularity,
    retune_strategies, retune_folds, min_oos_sharpe, max_overfit_gap, search_mode, max_combos,
    require_clear_noise_bar,
) -> tuple[str, dict]:
    from live.auto_retune import retune

    print("Re-tuning: re-running walk-forward search on recent data...")
    outcome = retune(
        current_strategy_name, current_params, instrument, granularity,
        candidate_strategies=retune_strategies, n_folds=retune_folds,
        min_oos_sharpe=min_oos_sharpe, max_overfit_gap=max_overfit_gap,
        search_mode=search_mode, max_combos=max_combos,
        require_clear_noise_bar=require_clear_noise_bar,
    )
    sig = outcome.significance
    record_retune_event(
        current_strategy_name, json.dumps(current_params),
        outcome.strategy_name, json.dumps(outcome.params),
        outcome.mean_test_sharpe, outcome.overfit_gap, outcome.changed,
        n_trials=sig.n_trials, expected_max_null=sig.expected_max_null, clears_null_bar=sig.clears_null_bar,
    )
    append_history(
        current_strategy_name, current_params, outcome.strategy_name, outcome.params,
        outcome.changed, outcome.mean_test_sharpe, outcome.overfit_gap,
        n_trials=sig.n_trials, expected_max_null=sig.expected_max_null, clears_null_bar=sig.clears_null_bar,
    )
    write_current_strategy(
        outcome.strategy_name, outcome.params, source="auto_retune",
        mean_test_sharpe=outcome.mean_test_sharpe, overfit_gap=outcome.overfit_gap,
        n_trials=sig.n_trials, expected_max_null=sig.expected_max_null, clears_null_bar=sig.clears_null_bar,
    )
    set_last_retune_at(dt.datetime.utcnow().isoformat())
    notify_retune(
        outcome.changed, current_strategy_name, current_params,
        outcome.strategy_name, outcome.params, outcome.mean_test_sharpe, outcome.overfit_gap,
        n_trials=sig.n_trials, expected_max_null=sig.expected_max_null, clears_null_bar=sig.clears_null_bar,
    )
    print(
        f"  -> {sig.n_trials} trials searched, noise benchmark {sig.expected_max_null:.2f} "
        f"({'clears' if sig.clears_null_bar else 'does NOT clear'} it)"
    )
    if outcome.changed:
        print(f"  -> switching to {outcome.strategy_name}{outcome.params} "
              f"(OOS Sharpe {outcome.mean_test_sharpe:.2f}, overfit gap {outcome.overfit_gap:.2f})")
    else:
        print("  -> no candidate cleared the guardrails, keeping current strategy/params.")
    return outcome.strategy_name, outcome.params
