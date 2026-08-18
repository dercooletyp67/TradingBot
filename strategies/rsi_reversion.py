import pandas as pd

from .base import register


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


@register(
    "rsi_reversion",
    param_grid={"period": [7, 14, 21], "oversold": [20, 25, 30], "overbought": [70, 75, 80]},
    description="Mean-reversion: long when RSI is oversold, short when overbought, flat otherwise.",
)
def generate_signals(
    df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70
) -> pd.Series:
    rsi = _rsi(df["close"], period)
    signal = pd.Series(0, index=df.index)
    signal[rsi < oversold] = 1
    signal[rsi > overbought] = -1
    return signal.replace(0, pd.NA).ffill().fillna(0)
