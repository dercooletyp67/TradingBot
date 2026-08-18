import pandas as pd

from .base import register


@register(
    "macd_momentum",
    param_grid={"fast": [8, 12, 16], "slow": [21, 26, 35], "signal": [5, 9, 12]},
    description="Long when MACD line is above its signal line, short when below.",
)
def generate_signals(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    if fast >= slow:
        return pd.Series(0, index=df.index)
    fast_ema = df["close"].ewm(span=fast, adjust=False).mean()
    slow_ema = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()

    sig = pd.Series(0, index=df.index)
    sig[macd_line > signal_line] = 1
    sig[macd_line < signal_line] = -1
    return sig
