"""Optional Discord notifications for trade fills and strategy switches.

Silently does nothing if DISCORD_WEBHOOK_URL isn't set (see config.py) --
notifications are a nice-to-have, never something that should crash a tick
or block a trade if Discord is unreachable.
"""
from __future__ import annotations

import requests

from config import DISCORD_WEBHOOK_URL


def send_discord_message(content: str) -> None:
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=10)
    except requests.RequestException as e:
        print(f"Discord notification failed (continuing anyway): {e}")


def notify_trade(strategy_name: str, instrument: str, side: str, units: int, price: float, pnl: float) -> None:
    emoji = "\N{LARGE GREEN CIRCLE}" if side == "buy" else "\N{LARGE RED CIRCLE}"
    pnl_str = f"{pnl:+.2f}" if pnl else "0.00"
    send_discord_message(
        f"{emoji} **{side.upper()}** {units} {instrument} @ {price:.5f} "
        f"(strategy: `{strategy_name}`, realized PnL: {pnl_str})"
    )


def notify_retune(
    changed: bool,
    old_strategy: str | None,
    old_params: dict | None,
    new_strategy: str,
    new_params: dict,
    mean_test_sharpe: float | None,
    overfit_gap: float | None,
    n_trials: int | None = None,
    expected_max_null: float | None = None,
    clears_null_bar: bool | None = None,
) -> None:
    sharpe_str = f"{mean_test_sharpe:.2f}" if mean_test_sharpe is not None else "n/a"
    gap_str = f"{overfit_gap:.2f}" if overfit_gap is not None else "n/a"
    noise_note = ""
    if n_trials is not None and expected_max_null is not None:
        clears = "clears" if clears_null_bar else "does NOT clear"
        noise_note = f"\n{n_trials} trials searched, noise benchmark {expected_max_null:.2f} -- {clears} it"
    if changed:
        send_discord_message(
            f"\N{ROBOT FACE} **Re-tune: switched strategy**\n"
            f"`{old_strategy}{old_params}` -> `{new_strategy}{new_params}`\n"
            f"OOS Sharpe: {sharpe_str}, overfit gap: {gap_str}{noise_note}"
        )
    else:
        send_discord_message(
            f"\N{ROBOT FACE} Re-tune ran, kept `{new_strategy}{new_params}` "
            f"(best candidate OOS Sharpe {sharpe_str}, overfit gap {gap_str}, "
            f"didn't clear the guardrails){noise_note}"
        )


def notify_kill_switch(drawdown_pct: float, max_drawdown_pct: float) -> None:
    send_discord_message(
        f"\N{OCTAGONAL SIGN} **Kill switch tripped** -- drawdown {drawdown_pct:.1f}% exceeded the "
        f"-{max_drawdown_pct:.1f}% limit. Position flattened, trading halted until manually resumed "
        f"(`--resume-trading`)."
    )
