"""Strategy interface.

A strategy is just a function `generate_signals(df, **params) -> pd.Series`
that maps OHLC data to a position series of -1 (short), 0 (flat), or 1 (long)
for each bar. PARAM_GRID declares the parameter values the optimizer should
sweep over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

STRATEGIES: dict[str, "Strategy"] = {}


@dataclass
class Strategy:
    name: str
    generate_signals: Callable[..., pd.Series]
    param_grid: dict[str, list] = field(default_factory=dict)
    description: str = ""


def register(name: str, param_grid: dict[str, list], description: str = ""):
    def decorator(fn: Callable[..., pd.Series]):
        STRATEGIES[name] = Strategy(
            name=name, generate_signals=fn, param_grid=param_grid, description=description
        )
        return fn

    return decorator


def get_strategy(name: str) -> Strategy:
    if name not in STRATEGIES:
        raise KeyError(f"Unknown strategy '{name}'. Available: {list(STRATEGIES)}")
    return STRATEGIES[name]
