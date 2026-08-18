import pandas as pd

from .base import register


@register(
    "bollinger_reversion",
    param_grid={"period": [10, 20, 30], "num_std": [1.5, 2.0, 2.5, 3.0]},
    description="Mean-reversion: long when price closes below the lower Bollinger Band, "
    "short when above the upper band, holds until the opposite band is touched.",
)
def generate_signals(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.Series:
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std

    sig = pd.Series(0, index=df.index)
    sig[df["close"] < lower] = 1
    sig[df["close"] > upper] = -1
    return sig.replace(0, pd.NA).ffill().fillna(0)
