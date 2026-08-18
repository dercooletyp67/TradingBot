import pandas as pd

from .base import register


@register(
    "breakout",
    param_grid={"lookback": [10, 20, 55, 100]},
    description="Donchian channel breakout: long on new N-bar high, short on new N-bar low.",
)
def generate_signals(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    upper = df["high"].rolling(lookback).max()
    lower = df["low"].rolling(lookback).min()
    signal = pd.Series(0, index=df.index)
    signal[df["close"] >= upper.shift(1)] = 1
    signal[df["close"] <= lower.shift(1)] = -1
    return signal.replace(0, pd.NA).ffill().fillna(0)
