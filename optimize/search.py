"""Walk-forward parameter sweep.

The naive way to "test 10,000 strategies" is to grid-search parameters and
pick whichever one had the best return on the full historical dataset. That
number is almost meaningless -- with enough combinations, some will look
great purely by curve-fitting noise in that specific data.

Instead this does walk-forward validation: the data is split into several
chronological folds. For each parameter combination we compute performance
on the in-sample (train) portion of each fold AND the out-of-sample (test)
portion that immediately follows it. Combinations are ranked by mean
out-of-sample Sharpe, not in-sample. The gap between in-sample and
out-of-sample performance is reported so you can see how much of the
in-sample "edge" was just overfitting.
"""
from __future__ import annotations

import itertools
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtest.engine import run_backtest
from strategies.base import Strategy


@dataclass
class FoldResult:
    train_sharpe: float
    test_sharpe: float
    train_return_pct: float
    test_return_pct: float


@dataclass
class SweepResult:
    params: dict
    mean_test_sharpe: float
    mean_train_sharpe: float
    mean_test_return_pct: float
    overfit_gap: float  # mean_train_sharpe - mean_test_sharpe
    folds: list[FoldResult]


def walk_forward_folds(n_bars: int, n_folds: int = 4) -> list[tuple[slice, slice]]:
    fold_size = n_bars // (n_folds + 1)
    if fold_size < 10:
        raise ValueError("Not enough bars for walk-forward folds; use more history or fewer folds.")
    folds = []
    for i in range(n_folds):
        train_end = fold_size * (i + 1)
        test_end = fold_size * (i + 2)
        folds.append((slice(0, train_end), slice(train_end, test_end)))
    return folds


def _slice_sharpe_and_return(returns: pd.Series, bars_per_year: float) -> tuple[float, float]:
    if len(returns) == 0:
        return 0.0, 0.0
    std = returns.std()
    sharpe = (returns.mean() / std) * np.sqrt(bars_per_year) if std and std > 0 else 0.0
    total_return_pct = ((1 + returns).prod() - 1) * 100
    return float(sharpe), float(total_return_pct)


_WORKER_DF: pd.DataFrame | None = None


def _init_worker(df: pd.DataFrame) -> None:
    global _WORKER_DF
    _WORKER_DF = df


def _evaluate_combo(
    generate_signals,
    params: dict,
    folds: list[tuple[slice, slice]],
    bars_per_year: float,
    cost_bps: float,
) -> SweepResult | None:
    df = _WORKER_DF
    try:
        signal = generate_signals(df, **params)
    except Exception:
        return None

    result = run_backtest(df, signal, cost_bps=cost_bps, extract_trades=False)
    returns = result.returns

    fold_results = []
    for train_slice, test_slice in folds:
        train_sharpe, train_ret = _slice_sharpe_and_return(returns.iloc[train_slice], bars_per_year)
        test_sharpe, test_ret = _slice_sharpe_and_return(returns.iloc[test_slice], bars_per_year)
        fold_results.append(
            FoldResult(
                train_sharpe=train_sharpe,
                test_sharpe=test_sharpe,
                train_return_pct=train_ret,
                test_return_pct=test_ret,
            )
        )

    mean_test_sharpe = float(np.mean([f.test_sharpe for f in fold_results]))
    mean_train_sharpe = float(np.mean([f.train_sharpe for f in fold_results]))
    mean_test_return = float(np.mean([f.test_return_pct for f in fold_results]))

    return SweepResult(
        params=params,
        mean_test_sharpe=mean_test_sharpe,
        mean_train_sharpe=mean_train_sharpe,
        mean_test_return_pct=mean_test_return,
        overfit_gap=mean_train_sharpe - mean_test_sharpe,
        folds=fold_results,
    )


def param_combinations(
    param_grid: dict[str, list],
    search_mode: str = "grid",
    max_combos: int | None = None,
    seed: int = 42,
) -> list[dict]:
    """search_mode='grid' walks every combination (optionally down-sampled to
    max_combos if that's smaller than the full grid). search_mode='random'
    draws max_combos distinct combinations without ever materializing the
    full grid -- the only practical option once a grid gets huge, since it
    lets you trade search coverage for wall-clock time directly instead of
    exhaustively evaluating combinations you'll never have time to reach.
    """
    keys = list(param_grid.keys())
    total_space = 1
    for values in param_grid.values():
        total_space *= len(values)

    if search_mode == "random" and max_combos is not None and max_combos < total_space:
        rng = random.Random(seed)
        seen: set[tuple] = set()
        combos = []
        while len(combos) < max_combos:
            candidate = tuple(rng.choice(param_grid[k]) for k in keys)
            if candidate in seen:
                continue
            seen.add(candidate)
            combos.append(dict(zip(keys, candidate)))
        return combos

    all_combos = [dict(zip(keys, combo)) for combo in itertools.product(*(param_grid[k] for k in keys))]
    if max_combos is not None and max_combos < len(all_combos):
        rng = random.Random(seed)
        return rng.sample(all_combos, max_combos)
    return all_combos


def run_sweep(
    df: pd.DataFrame,
    strategy: Strategy,
    bars_per_year: float,
    n_folds: int = 4,
    cost_bps: float = 2.0,
    max_workers: int | None = None,
    top_n: int = 10,
    search_mode: str = "grid",
    max_combos: int | None = None,
) -> list[SweepResult]:
    """Search strategy.param_grid with walk-forward validation.
    Returns the top_n combinations ranked by mean out-of-sample Sharpe.
    """
    folds = walk_forward_folds(len(df), n_folds=n_folds)
    combos = param_combinations(strategy.param_grid, search_mode=search_mode, max_combos=max_combos)

    results: list[SweepResult] = []
    with ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker, initargs=(df,)) as pool:
        futures = [
            pool.submit(
                _evaluate_combo, strategy.generate_signals, params, folds, bars_per_year, cost_bps
            )
            for params in combos
        ]
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                results.append(res)

    results.sort(key=lambda r: r.mean_test_sharpe, reverse=True)
    return results[:top_n]
