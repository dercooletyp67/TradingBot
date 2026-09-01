"""Thin wrapper around the OANDA v20 REST API.

Only ever points at OANDA_HOST, which config.py hard-pins to the practice
(demo) environment -- see config.py for the guard that refuses to run
against a live real-money account.
"""
from __future__ import annotations

import pandas as pd
import requests

from config import OANDA_ACCOUNT_ID, OANDA_API_KEY, OANDA_HOST


class OandaClient:
    def __init__(self):
        if not OANDA_API_KEY or not OANDA_ACCOUNT_ID:
            raise RuntimeError("OANDA_API_KEY / OANDA_ACCOUNT_ID not set. Copy .env.example to .env.")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {OANDA_API_KEY}"})
        self.base = f"{OANDA_HOST}/v3"
        self.account_id = OANDA_ACCOUNT_ID

    def get_account_summary(self) -> dict:
        r = self.session.get(f"{self.base}/accounts/{self.account_id}/summary", timeout=15)
        r.raise_for_status()
        return r.json()["account"]

    def get_open_units(self, instrument: str) -> int:
        r = self.session.get(f"{self.base}/accounts/{self.account_id}/positions/{instrument}", timeout=15)
        if r.status_code == 404:
            return 0
        r.raise_for_status()
        pos = r.json()["position"]
        long_units = int(pos["long"]["units"])
        short_units = int(pos["short"]["units"])
        return long_units + short_units

    def get_recent_candles(self, instrument: str, granularity: str, count: int) -> pd.DataFrame:
        r = self.session.get(
            f"{self.base}/instruments/{instrument}/candles",
            params={"granularity": granularity, "count": count, "price": "M"},
            timeout=15,
        )
        r.raise_for_status()
        rows = []
        for c in r.json()["candles"]:
            if not c["complete"]:
                continue
            mid = c["mid"]
            rows.append(
                {
                    "time": pd.Timestamp(c["time"]),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(c["volume"]),
                }
            )
        return pd.DataFrame(rows).set_index("time")

    def place_market_order(self, instrument: str, units: float) -> dict:
        """units > 0 buys, units < 0 sells. Rounded to a whole number --
        real OANDA forex/CFD instruments don't accept fractional units,
        unlike the simulated broker (which needs fractions for high-priced
        assets like BTC-USD; not a concern here since OANDA doesn't offer
        crypto anyway)."""
        body = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(round(units)),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        r = self.session.post(f"{self.base}/accounts/{self.account_id}/orders", json=body, timeout=15)
        r.raise_for_status()
        return r.json()
