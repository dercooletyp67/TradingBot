"""Historical candle data for backtesting.

Two sources:
  - fetch_oanda_candles(): real historical forex data from OANDA (requires
    OANDA_API_KEY in .env). Works even though your account is a demo/practice
    account -- historical price data is the same real market data either way.
  - generate_synthetic_ohlc(): a fake random-walk price series, useful for
    smoke-testing the backtest engine without needing API credentials yet.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import requests

from config import OANDA_API_KEY, OANDA_HOST

MAX_CANDLES_PER_REQUEST = 5000

# Yahoo Finance forex tickers and interval names, and how far back each
# intraday interval is allowed to go (Yahoo's own limits, not ours).
YF_SYMBOL_MAP = {
    "EUR_USD": "EURUSD=X",
    "GBP_USD": "GBPUSD=X",
    "USD_JPY": "USDJPY=X",
    "AUD_USD": "AUDUSD=X",
    "USD_CHF": "USDCHF=X",
    "USD_CAD": "USDCAD=X",
    "NZD_USD": "NZDUSD=X",
}
YF_GRANULARITY_MAP = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m", "H1": "60m", "D": "1d",
}
YF_MAX_PERIOD = {
    "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "60m": "730d", "1d": "10y",
}


def fetch_yfinance_candles(instrument: str, granularity: str, count: int | None = None) -> pd.DataFrame:
    """Real forex price data from Yahoo Finance -- no account, no API key.

    instrument: OANDA-style name, e.g. "EUR_USD" (mapped to Yahoo's "EURUSD=X").
    granularity: OANDA-style code, e.g. "H1" (mapped to Yahoo's "60m").
    count: if set, only the most recent N bars are returned.
    """
    import yfinance as yf

    symbol = YF_SYMBOL_MAP.get(instrument, instrument)
    interval = YF_GRANULARITY_MAP.get(granularity, granularity)
    period = YF_MAX_PERIOD.get(interval, "60d")

    df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
    if df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index.name = "time"

    if count:
        df = df.tail(count)
    return df


def fetch_oanda_candles(
    instrument: str,
    granularity: str,
    start: dt.datetime,
    end: dt.datetime,
    price: str = "M",
) -> pd.DataFrame:
    """Fetch historical candles from OANDA, paginating as needed.

    instrument: e.g. "EUR_USD"
    granularity: e.g. "M1", "M5", "M15", "H1", "H4", "D"
    price: "M" (midpoint), "B" (bid), or "A" (ask)
    """
    if not OANDA_API_KEY:
        raise RuntimeError("OANDA_API_KEY is not set. Copy .env.example to .env and fill it in.")

    headers = {"Authorization": f"Bearer {OANDA_API_KEY}"}
    url = f"{OANDA_HOST}/v3/instruments/{instrument}/candles"

    all_rows = []
    cursor = start
    while cursor < end:
        params = {
            "granularity": granularity,
            "price": price,
            "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": MAX_CANDLES_PER_REQUEST,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        candles = resp.json().get("candles", [])
        if not candles:
            break

        for c in candles:
            if not c["complete"]:
                continue
            mid = c.get(price_key(price), c.get("mid"))
            all_rows.append(
                {
                    "time": pd.Timestamp(c["time"]),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(c["volume"]),
                }
            )

        last_time = pd.Timestamp(candles[-1]["time"]).to_pydatetime()
        if last_time <= cursor:
            break
        cursor = last_time + dt.timedelta(seconds=1)

        if len(candles) < MAX_CANDLES_PER_REQUEST:
            break

    df = pd.DataFrame(all_rows).drop_duplicates(subset="time").sort_values("time")
    df = df.set_index("time")
    return df


def price_key(price: str) -> str:
    return {"M": "mid", "B": "bid", "A": "ask"}[price]


def generate_synthetic_ohlc(
    n_bars: int = 5000,
    start_price: float = 1.1000,
    freq: str = "1h",
    seed: int | None = 42,
    annual_vol: float = 0.08,
) -> pd.DataFrame:
    """Generate a fake random-walk OHLC series for smoke-testing, shaped like
    a forex pair (small price, tight ranges)."""
    rng = np.random.default_rng(seed)
    bars_per_year = pd.Timedelta("365d") / pd.Timedelta(freq)
    bar_vol = annual_vol / np.sqrt(bars_per_year)

    returns = rng.normal(loc=0.0, scale=bar_vol, size=n_bars)
    close = start_price * np.cumprod(1 + returns)

    open_ = np.roll(close, 1)
    open_[0] = start_price
    high = np.maximum(open_, close) * (1 + rng.uniform(0, bar_vol, n_bars))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, bar_vol, n_bars))
    volume = rng.integers(100, 1000, n_bars)

    index = pd.date_range(end=pd.Timestamp.utcnow(), periods=n_bars, freq=freq)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )
