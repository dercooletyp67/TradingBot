import pytest

from dashboard.stats import compute_stats


def test_no_snapshots_returns_safe_empty_defaults_not_a_crash():
    stats = compute_stats(snapshots=[], trades=[])

    assert stats["current_balance"] is None
    assert stats["total_return_pct"] == 0
    assert stats["num_trades"] == 0


def test_total_return_reflects_balance_plus_unrealized_pnl():
    snapshots = [
        {"balance": 10_000.0, "unrealized_pnl": 0.0},
        {"balance": 10_000.0, "unrealized_pnl": 500.0},  # up 5% unrealized
    ]
    stats = compute_stats(snapshots, trades=[])

    assert stats["current_balance"] == 10_500.0
    assert stats["total_return_pct"] == pytest.approx(5.0)


def test_max_drawdown_measured_from_running_peak():
    snapshots = [
        {"balance": 10_000.0, "unrealized_pnl": 0.0},
        {"balance": 12_000.0, "unrealized_pnl": 0.0},  # new peak
        {"balance": 9_000.0, "unrealized_pnl": 0.0},   # -25% from peak
        {"balance": 11_000.0, "unrealized_pnl": 0.0},  # recovers, but drawdown already recorded
    ]
    stats = compute_stats(snapshots, trades=[])

    assert stats["max_drawdown_pct"] == pytest.approx(-25.0)


def test_win_rate_only_counts_closed_trades_with_pnl():
    trades = [
        {"pnl": 10.0},
        {"pnl": -5.0},
        {"pnl": None},  # e.g. a position-opening trade with no realized pnl yet
    ]
    snapshots = [{"balance": 10_000.0, "unrealized_pnl": 0.0}]
    stats = compute_stats(snapshots, trades)

    assert stats["num_trades"] == 3  # counts all trades
    assert stats["win_rate_pct"] == pytest.approx(50.0)  # but win rate ignores the None
