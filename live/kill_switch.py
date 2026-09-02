"""Max-drawdown kill switch: if equity falls too far below its all-time
peak, the position gets flattened and trading halts until manually
resumed (see storage.db.resume_trading).

There's a real difference between "the strategy is having a bad stretch"
(normal, expected, no action needed -- drawdowns happen even to strategies
that work) and "something is badly wrong" (a bug, a data problem, a market
regime the strategy has no business being in). This doesn't try to tell
those apart -- it just stops the bleeding at a pre-agreed line and waits
for a human to look, which is the right default when you can't tell which
situation you're actually in.
"""
from __future__ import annotations

from storage.db import get_peak_equity, set_peak_equity


def check_drawdown(current_equity: float, max_drawdown_pct: float | None) -> tuple[bool, float]:
    """Returns (should_halt_now, current_drawdown_pct). Updates peak_equity
    as a side effect regardless of whether max_drawdown_pct is set, so the
    peak stays accurate if the kill switch gets turned on later."""
    peak = max(get_peak_equity(), current_equity)
    set_peak_equity(peak)
    drawdown_pct = (current_equity / peak - 1) * 100 if peak > 0 else 0.0

    if max_drawdown_pct is None or max_drawdown_pct <= 0:
        return False, drawdown_pct
    return drawdown_pct <= -abs(max_drawdown_pct), drawdown_pct
