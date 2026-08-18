from .base import STRATEGIES, get_strategy  # noqa: F401

# Import strategy modules so they self-register via @register.
from . import sma_cross, rsi_reversion, breakout, macd_momentum, bollinger_reversion  # noqa: F401,E402
