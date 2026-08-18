"""Human-readable record of what the bot has "learned" -- i.e. every
walk-forward search decision it has made -- written as plain files in
learn/, not just buried in SQLite.

current_strategy.json: the strategy/params currently live, and the
    out-of-sample stats that justified picking it (if it came from a
    re-tune rather than the initial seed).
history.jsonl: one JSON line per re-tune cycle, oldest first, append-only.
    Every cycle is recorded, whether it switched strategies or not, so you
    can see what it considered and why it did or didn't change.

See learn/README.md for what these numbers do and don't mean.
"""
from __future__ import annotations

import datetime as dt
import json

from config import LEARN_DIR

CURRENT_STRATEGY_FILE = LEARN_DIR / "current_strategy.json"
HISTORY_FILE = LEARN_DIR / "history.jsonl"

README_CONTENT = """# What the bot has learned

This folder is a plain-file view into the same walk-forward parameter
search described in the main README -- there's no model here, just a
record of which strategy/params were live and why.

- **current_strategy.json** -- what's running right now, and the
  out-of-sample Sharpe / overfit gap that justified it (if it came from a
  re-tune; "seed" entries were just the starting point you passed on the
  command line, not yet validated).
- **history.jsonl** -- one line per re-tune cycle, oldest first. Every
  cycle is logged whether it switched strategies or not. Each line has:
  `timestamp`, `old_strategy`/`old_params`, `new_strategy`/`new_params`,
  `changed`, `mean_test_sharpe` (out-of-sample), `overfit_gap`
  (in-sample Sharpe minus out-of-sample Sharpe -- large values mean the
  pick looked good mostly because it was fit to the training window).

Read `mean_test_sharpe` and `overfit_gap` skeptically: this is a search
over historical data re-run periodically, not a model that accumulates
understanding. A high out-of-sample Sharpe in one cycle is not a promise
about the next one.
"""


def _ensure_dir() -> None:
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    readme = LEARN_DIR / "README.md"
    if not readme.exists():
        readme.write_text(README_CONTENT)


def write_current_strategy(
    strategy_name: str,
    params: dict,
    source: str,
    mean_test_sharpe: float | None = None,
    overfit_gap: float | None = None,
) -> None:
    _ensure_dir()
    data = {
        "strategy": strategy_name,
        "params": params,
        "source": source,  # "seed" (from CLI args) or "auto_retune"
        "mean_test_sharpe": mean_test_sharpe,
        "overfit_gap": overfit_gap,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    CURRENT_STRATEGY_FILE.write_text(json.dumps(data, indent=2))


def append_history(
    old_strategy: str | None,
    old_params: dict | None,
    new_strategy: str,
    new_params: dict,
    changed: bool,
    mean_test_sharpe: float | None,
    overfit_gap: float | None,
) -> None:
    _ensure_dir()
    entry = {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "old_strategy": old_strategy,
        "old_params": old_params,
        "new_strategy": new_strategy,
        "new_params": new_params,
        "changed": changed,
        "mean_test_sharpe": mean_test_sharpe,
        "overfit_gap": overfit_gap,
    }
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
