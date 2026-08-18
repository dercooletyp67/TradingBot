"""Start the live paper-trading loop.

Default backend needs no account at all (Yahoo Finance data + a locally
tracked fake balance). Pass --broker oanda to route through a real OANDA
demo account instead.

Examples:
  python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
      --instrument EUR_USD --granularity H1 --units 1000 --poll-seconds 60

  python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
      --broker oanda --instrument EUR_USD --granularity H1

  # Re-search parameters every 6 hours and auto-switch if a candidate clears
  # the guardrails on out-of-sample Sharpe and overfit gap:
  python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
      --instrument EUR_USD --granularity H1 --auto-retune-hours 6

  # --once: do a single check-and-maybe-trade cycle then exit, resuming
  # from whatever's already persisted rather than resetting to this seed.
  # For cron-driven runs (see .github/workflows/paper_trade.yml) -- not
  # meant for interactive/desktop use, where the loop above is simpler.
  python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
      --instrument EUR_USD --granularity H1 --once
"""
from __future__ import annotations

import argparse

from live.paper_trader import run_paper_trader, run_paper_trader_once
from run_backtest import parse_params


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--params", default="")
    ap.add_argument("--instrument", default="EUR_USD")
    ap.add_argument("--granularity", default="H1")
    ap.add_argument("--units", type=int, default=1000, help="position size in units when fully long/short")
    ap.add_argument("--poll-seconds", type=int, default=60)
    ap.add_argument("--broker", choices=["simulated", "oanda"], default="simulated")
    ap.add_argument("--starting-balance", type=float, default=10_000.0, help="simulated broker only")

    ap.add_argument(
        "--auto-retune-hours", type=float, default=None,
        help="if set, re-run the walk-forward search every N hours and switch strategy/params "
        "if a candidate clears the guardrails (off by default)",
    )
    ap.add_argument(
        "--retune-strategies", default="all",
        help="comma-separated strategy names to consider when re-tuning, or 'all' (default)",
    )
    ap.add_argument("--retune-folds", type=int, default=4)
    ap.add_argument("--retune-min-oos-sharpe", type=float, default=0.0)
    ap.add_argument("--retune-max-overfit-gap", type=float, default=1.5)
    ap.add_argument("--retune-search", choices=["grid", "random"], default="grid")
    ap.add_argument("--retune-max-combos", type=int, default=None)
    ap.add_argument(
        "--once", action="store_true",
        help="do a single check-and-maybe-trade cycle then exit, instead of looping forever "
        "(for cron-driven runs, e.g. GitHub Actions)",
    )
    args = ap.parse_args()

    retune_strategies = None if args.retune_strategies == "all" else args.retune_strategies.split(",")

    common_kwargs = dict(
        strategy_name=args.strategy,
        params=parse_params(args.params),
        instrument=args.instrument,
        granularity=args.granularity,
        units_per_trade=args.units,
        broker=args.broker,
        starting_balance=args.starting_balance,
        auto_retune_hours=args.auto_retune_hours,
        retune_strategies=retune_strategies,
        retune_folds=args.retune_folds,
        retune_min_oos_sharpe=args.retune_min_oos_sharpe,
        retune_max_overfit_gap=args.retune_max_overfit_gap,
        retune_search_mode=args.retune_search,
        retune_max_combos=args.retune_max_combos,
    )

    if args.once:
        run_paper_trader_once(**common_kwargs)
    else:
        run_paper_trader(poll_seconds=args.poll_seconds, **common_kwargs)


if __name__ == "__main__":
    main()
