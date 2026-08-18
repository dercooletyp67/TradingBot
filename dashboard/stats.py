"""Dashboard summary stats, computed from equity/trade history. Shared by
the local FastAPI server (dashboard/server.py) and the static-site export
used for GitHub Pages (export_dashboard_data.py) so the two dashboards never
disagree about how a number is calculated.
"""
from __future__ import annotations


def compute_stats(snapshots: list[dict], trades: list[dict]) -> dict:
    if not snapshots:
        return {
            "current_balance": None,
            "starting_balance": None,
            "total_return_pct": 0,
            "max_drawdown_pct": 0,
            "num_trades": len(trades),
            "win_rate_pct": 0,
        }

    balances = [s["balance"] + s["unrealized_pnl"] for s in snapshots]
    starting = balances[0]
    current = balances[-1]
    total_return_pct = (current / starting - 1) * 100 if starting else 0

    peak = balances[0]
    max_dd = 0.0
    for b in balances:
        peak = max(peak, b)
        dd = (b / peak - 1) * 100 if peak else 0
        max_dd = min(max_dd, dd)

    closed = [t for t in trades if t["pnl"] is not None]
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = (len(wins) / len(closed) * 100) if closed else 0

    return {
        "current_balance": current,
        "starting_balance": starting,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd,
        "num_trades": len(trades),
        "win_rate_pct": win_rate,
    }
