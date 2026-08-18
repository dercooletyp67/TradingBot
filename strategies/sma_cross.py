import pandas as pd

from .base import register


@register(
    "sma_cross",
    param_grid={"fast": [5, 10, 15, 20], "slow": [30, 50, 100, 200]},
    description="Long when fast SMA is above slow SMA, short when below.",
)
def generate_signals(df: pd.DataFrame, fast: int = 10, slow: int = 50) -> pd.Series:
    if fast >= slow:
        return pd.Series(0, index=df.index)
    fast_sma = df["close"].rolling(fast).mean()
    slow_sma = df["close"].rolling(slow).mean()
    signal = pd.Series(0, index=df.index)
    signal[fast_sma > slow_sma] = 1
    signal[fast_sma < slow_sma] = -1
    return signal
