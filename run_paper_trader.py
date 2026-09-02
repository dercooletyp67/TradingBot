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

  # Volatility-based position sizing instead of a fixed unit count: risk
  # ~1% of balance per trade, position size scaled down when ATR is high:
  python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
      --instrument EUR_USD --granularity H1 --position-sizing volatility --risk-pct 0.01

  # Kill switch: flatten and halt if equity ever drops 20% below its peak:
  python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
      --instrument EUR_USD --granularity H1 --max-drawdown-pct 20

  # Clear a tripped kill switch and resume trading:
  python run_paper_trader.py --strategy sma_cross --instrument EUR_USD --granularity H1 --resume-trading --once
"""
from __future__ import annotations

import argparse

from live.paper_trader import run_paper_trader, run_paper_trader_once
from live.position_sizing import PositionSizingConfig
from run_backtest import parse_params
from storage.db import init_db, resume_trading


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--params", default="")
    ap.add_argument("--instrument", default="EUR_USD")
    ap.add_argument("--granularity", default="H1")
    ap.add_argument("--poll-seconds", type=int, default=60)

    ap.add_argument(
        "--position-sizing", choices=["fixed", "volatility"], default="fixed",
        help="'fixed': always trade --units. 'volatility': size units so a move of "
        "--atr-multiplier x ATR costs roughly --risk-pct of balance (default: fixed, "
        "for backward compatibility)",
    )
    ap.add_argument("--units", type=int, default=1000, help="units per trade, --position-sizing fixed only")
    ap.add_argument("--risk-pct", type=float, default=0.01, help="fraction of balance risked per trade, volatility sizing only")
    ap.add_argument("--atr-period", type=int, default=14)
    ap.add_argument("--atr-multiplier", type=float, default=1.5)
    ap.add_argument(
        "--min-notional", type=float, default=50.0,
        help="smallest position value worth opening, in account currency (volatility sizing only)",
    )
    ap.add_argument(
        "--max-notional-pct", type=float, default=0.5,
        help="largest position value as a fraction of balance, e.g. 0.5 = never more than half the "
        "account in one position (volatility sizing only)",
    )
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
        "--retune-ignore-noise-bar", action="store_true",
        help="allow a re-tune switch even if the best candidate doesn't beat the multiple-testing "
        "noise benchmark (see optimize/deflated_sharpe.py) -- off by default, i.e. the noise bar "
        "is required to clear by default",
    )
    ap.add_argument(
        "--max-drawdown-pct", type=float, default=None,
        help="kill switch: flatten the position and halt all trading once equity falls this many "
        "percent below its all-time peak (e.g. 20). Off by default. Clear a tripped switch with "
        "--resume-trading",
    )
    ap.add_argument(
        "--resume-trading", action="store_true",
        help="clear a tripped kill switch, then proceed with the tick/loop as normal",
    )
    ap.add_argument(
        "--once", action="store_true",
        help="do a single check-and-maybe-trade cycle then exit, instead of looping forever "
        "(for cron-driven runs, e.g. GitHub Actions)",
    )
    args = ap.parse_args()

    if args.resume_trading:
        init_db()
        resume_trading()
        print("Kill switch cleared, resuming trading.")

    retune_strategies = None if args.retune_strategies == "all" else args.retune_strategies.split(",")

    position_sizing = PositionSizingConfig(
        mode=args.position_sizing,
        fixed_units=args.units,
        risk_pct=args.risk_pct,
        atr_period=args.atr_period,
        atr_multiplier=args.atr_multiplier,
        min_notional=args.min_notional,
        max_notional_pct=args.max_notional_pct,
    )

    common_kwargs = dict(
        strategy_name=args.strategy,
        params=parse_params(args.params),
        instrument=args.instrument,
        granularity=args.granularity,
        position_sizing=position_sizing,
        broker=args.broker,
        starting_balance=args.starting_balance,
        auto_retune_hours=args.auto_retune_hours,
        retune_strategies=retune_strategies,
        retune_folds=args.retune_folds,
        retune_min_oos_sharpe=args.retune_min_oos_sharpe,
        retune_max_overfit_gap=args.retune_max_overfit_gap,
        retune_search_mode=args.retune_search,
        retune_max_combos=args.retune_max_combos,
        retune_require_clear_noise_bar=not args.retune_ignore_noise_bar,
        max_drawdown_pct=args.max_drawdown_pct,
    )

    if args.once:
        run_paper_trader_once(**common_kwargs)
    else:
        run_paper_trader(poll_seconds=args.poll_seconds, **common_kwargs)


if __name__ == "__main__":
    main()
