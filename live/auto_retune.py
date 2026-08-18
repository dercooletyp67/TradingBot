"""Periodic re-optimization for the live paper trader.

This is what "the bot learns/adapts over time" actually means here: on a
schedule, re-run the same walk-forward search used by run_optimize.py on
recent data, and only switch the live strategy/params if a candidate clears
guardrails on BOTH out-of-sample Sharpe and the in-sample/out-of-sample gap.
If nothing clears the bar, it keeps running what it already had. This is
adaptation to changing market conditions, not a model that gets smarter on
its own -- it can just as easily rotate into a worse regime as a better one,
which is why the guardrails exist.
"""
from __future__ import annotations

from dataclasses import dataclass

from backtest.metrics import GRANULARITY_BARS_PER_YEAR
from data.fetch import fetch_yfinance_candles
from optimize.search import run_sweep
from strategies import STRATEGIES, get_strategy


@dataclass
class RetuneOutcome:
    changed: bool
    strategy_name: str
    params: dict
    mean_test_sharpe: float | None
    overfit_gap: float | None


def retune(
    current_strategy_name: str,
    current_params: dict,
    instrument: str,
    granularity: str,
    candidate_strategies: list[str] | None = None,
    n_folds: int = 4,
    cost_bps: float = 2.0,
    min_oos_sharpe: float = 0.0,
    max_overfit_gap: float = 1.5,
    history_bars: int = 5000,
    search_mode: str = "grid",
    max_combos: int | None = None,
) -> RetuneOutcome:
    names = candidate_strategies or list(STRATEGIES.keys())
    df = fetch_yfinance_candles(instrument, granularity, count=history_bars)
    bars_per_year = GRANULARITY_BARS_PER_YEAR.get(granularity, 252)

    best = None
    best_name = None
    for name in names:
        strat = get_strategy(name)
        for r in run_sweep(
            df, strat, bars_per_year, n_folds=n_folds, cost_bps=cost_bps,
            top_n=1, search_mode=search_mode, max_combos=max_combos,
        ):
            if best is None or r.mean_test_sharpe > best.mean_test_sharpe:
                best, best_name = r, name

    if best is None or best.mean_test_sharpe < min_oos_sharpe or best.overfit_gap > max_overfit_gap:
        return RetuneOutcome(
            changed=False,
            strategy_name=current_strategy_name,
            params=current_params,
            mean_test_sharpe=best.mean_test_sharpe if best else None,
            overfit_gap=best.overfit_gap if best else None,
        )

    changed = best_name != current_strategy_name or best.params != current_params
    return RetuneOutcome(
        changed=changed,
        strategy_name=best_name,
        params=best.params,
        mean_test_sharpe=best.mean_test_sharpe,
        overfit_gap=best.overfit_gap,
    )
