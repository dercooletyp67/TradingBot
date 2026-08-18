"""Backtest a single strategy + parameter set over historical data.

Examples:
  python run_backtest.py --strategy sma_cross --params fast=10,slow=50 --source synthetic
  python run_backtest.py --strategy sma_cross --params fast=10,slow=50 --instrument EUR_USD --granularity H1
  python run_backtest.py --strategy rsi_reversion --params period=14,oversold=30,overbought=70 \
      --source oanda --instrument EUR_USD --granularity H1 --start 2023-01-01 --end 2024-01-01
"""
from __future__ import annotations

import argparse
import datetime as dt

from backtest.engine import run_backtest
from backtest.metrics import GRANULARITY_BARS_PER_YEAR, compute_metrics
from data.fetch import fetch_oanda_candles, fetch_yfinance_candles, generate_synthetic_ohlc
from strategies import get_strategy


def parse_params(s: str | None) -> dict:
    if not s:
        return {}
    out = {}
    for pair in s.split(","):
        k, v = pair.split("=")
        out[k.strip()] = float(v) if "." in v else int(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--params", default="", help="comma-separated key=value, e.g. fast=10,slow=50")
    ap.add_argument("--instrument", default="EUR_USD")
    ap.add_argument("--granularity", default="H1")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (oanda source only)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (oanda source only)")
    ap.add_argument(
        "--source", choices=["yfinance", "oanda", "synthetic"], default="yfinance",
        help="yfinance needs no account; oanda needs OANDA_API_KEY in .env; synthetic is fake data",
    )
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--cost-bps", type=float, default=2.0)
    args = ap.parse_args()

    strategy = get_strategy(args.strategy)
    params = parse_params(args.params)

    if args.source == "synthetic":
        df = generate_synthetic_ohlc(n_bars=5000)
    elif args.source == "yfinance":
        df = fetch_yfinance_candles(args.instrument, args.granularity, count=5000)
    else:
        start = dt.datetime.fromisoformat(args.start) if args.start else dt.datetime.utcnow() - dt.timedelta(days=365)
        end = dt.datetime.fromisoformat(args.end) if args.end else dt.datetime.utcnow()
        df = fetch_oanda_candles(args.instrument, args.granularity, start, end)

    if df.empty:
        print("No data returned. Check instrument/date range/API credentials.")
        return

    signal = strategy.generate_signals(df, **params)
    result = run_backtest(df, signal, initial_capital=args.capital, cost_bps=args.cost_bps)
    bars_per_year = GRANULARITY_BARS_PER_YEAR.get(args.granularity, 252)
    metrics = compute_metrics(result, bars_per_year)

    print(f"\nStrategy: {args.strategy}{params}")
    print(f"Bars: {len(df)}  Range: {df.index[0]} -> {df.index[-1]}")
    print("-" * 50)
    for k, v in metrics.as_dict().items():
        print(f"{k:>20}: {v:,.2f}" if isinstance(v, float) else f"{k:>20}: {v}")


if __name__ == "__main__":
    main()
