"""Walk-forward grid search over a strategy's parameter grid (or every
bundled strategy) and report the combinations that held up out-of-sample.

Examples:
  python run_optimize.py --strategy sma_cross --source synthetic
  python run_optimize.py --strategy all --instrument EUR_USD --granularity H1 --folds 5 --top 10
  python run_optimize.py --strategy all --source oanda --instrument EUR_USD --granularity H1 \
      --start 2022-01-01 --end 2024-01-01 --folds 5 --top 10
"""
from __future__ import annotations

import argparse
import datetime as dt

from backtest.metrics import GRANULARITY_BARS_PER_YEAR
from data.fetch import fetch_oanda_candles, fetch_yfinance_candles, generate_synthetic_ohlc
from optimize.search import run_sweep
from strategies import STRATEGIES, get_strategy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="all", help="strategy name, or 'all'")
    ap.add_argument("--instrument", default="EUR_USD")
    ap.add_argument("--granularity", default="H1")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (oanda source only)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (oanda source only)")
    ap.add_argument(
        "--source", choices=["yfinance", "oanda", "synthetic"], default="yfinance",
        help="yfinance needs no account; oanda needs OANDA_API_KEY in .env; synthetic is fake data",
    )
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--cost-bps", type=float, default=2.0)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument(
        "--search", choices=["grid", "random"], default="grid",
        help="'grid' walks every combination; 'random' samples --max-combos of them, "
        "letting you cap wall-clock time on huge grids",
    )
    ap.add_argument("--max-combos", type=int, default=None, help="cap combos tested per strategy")
    args = ap.parse_args()

    if args.source == "synthetic":
        df = generate_synthetic_ohlc(n_bars=5000)
    elif args.source == "yfinance":
        df = fetch_yfinance_candles(args.instrument, args.granularity, count=5000)
    else:
        start = dt.datetime.fromisoformat(args.start) if args.start else dt.datetime.utcnow() - dt.timedelta(days=730)
        end = dt.datetime.fromisoformat(args.end) if args.end else dt.datetime.utcnow()
        df = fetch_oanda_candles(args.instrument, args.granularity, start, end)

    if df.empty:
        print("No data returned. Check instrument/date range/API credentials.")
        return

    bars_per_year = GRANULARITY_BARS_PER_YEAR.get(args.granularity, 252)
    strategy_names = list(STRATEGIES.keys()) if args.strategy == "all" else [args.strategy]

    total_combos = 0
    for name in strategy_names:
        strat = get_strategy(name)
        n_combos = 1
        for values in strat.param_grid.values():
            n_combos *= len(values)
        total_combos += n_combos if args.max_combos is None else min(n_combos, args.max_combos)

    print(f"Sweeping ~{total_combos} parameter combinations ({args.search} search) across "
          f"{len(strategy_names)} strategy(ies), {args.folds} walk-forward folds, on {len(df)} bars.\n")

    all_results = []
    for name in strategy_names:
        strat = get_strategy(name)
        results = run_sweep(
            df, strat, bars_per_year, n_folds=args.folds, cost_bps=args.cost_bps,
            max_workers=args.workers, top_n=args.top,
            search_mode=args.search, max_combos=args.max_combos,
        )
        for r in results:
            all_results.append((name, r))

    all_results.sort(key=lambda pair: pair[1].mean_test_sharpe, reverse=True)

    print(f"{'strategy':<16}{'params':<40}{'OOS Sharpe':>12}{'IS Sharpe':>12}{'overfit gap':>14}{'OOS ret%':>10}")
    print("-" * 104)
    for name, r in all_results[: args.top]:
        print(
            f"{name:<16}{str(r.params):<40}{r.mean_test_sharpe:>12.2f}{r.mean_train_sharpe:>12.2f}"
            f"{r.overfit_gap:>14.2f}{r.mean_test_return_pct:>10.2f}"
        )

    print(
        "\n'overfit gap' = in-sample Sharpe minus out-of-sample Sharpe. Large positive gaps mean the "
        "combo looked good mostly because it was fit to the training data, not because it's robust. "
        "Prefer combos with a high OOS Sharpe AND a small gap."
    )


if __name__ == "__main__":
    main()
