import pandas as pd
import pytest

from live.position_sizing import (
    PositionSizingConfig,
    average_true_range,
    compute_units,
    volatility_based_units,
)


def _flat_range_df(n=20, high_low_spread=1.0, close=100.0):
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame(
        {
            "open": [close] * n,
            "high": [close + high_low_spread / 2] * n,
            "low": [close - high_low_spread / 2] * n,
            "close": [close] * n,
        },
        index=index,
    )


def test_average_true_range_matches_constant_range():
    # constant high-low spread of 1.0 with unchanging close -> ATR converges to 1.0
    df = _flat_range_df(n=20, high_low_spread=1.0)
    atr = average_true_range(df, period=14)
    assert atr.iloc[-1] == pytest.approx(1.0)


def test_volatility_based_units_scales_inversely_with_atr():
    low_vol_units = volatility_based_units(balance=10_000, atr=0.001, risk_pct=0.01, atr_multiplier=1.5)
    high_vol_units = volatility_based_units(balance=10_000, atr=0.01, risk_pct=0.01, atr_multiplier=1.5)
    assert low_vol_units > high_vol_units


def test_volatility_based_units_respects_min_and_max():
    tiny_risk = volatility_based_units(balance=10_000, atr=100, risk_pct=0.01, min_units=100, max_units=100_000)
    assert tiny_risk == 100  # would compute below min, clamped up

    huge_risk = volatility_based_units(balance=10_000, atr=0.0000001, risk_pct=0.01, min_units=100, max_units=100_000)
    assert huge_risk == 100_000  # would compute above max, clamped down


def test_volatility_based_units_falls_back_to_min_on_bad_atr():
    assert volatility_based_units(balance=10_000, atr=0, min_units=250) == 250
    assert volatility_based_units(balance=10_000, atr=None, min_units=250) == 250
    assert volatility_based_units(balance=10_000, atr=float("nan"), min_units=250) == 250


def test_compute_units_fixed_mode_ignores_market_data():
    df = _flat_range_df()
    cfg = PositionSizingConfig(mode="fixed", fixed_units=777)
    assert compute_units(df, balance=10_000, cfg=cfg) == 777


def test_compute_units_volatility_mode_uses_atr():
    df = _flat_range_df(n=20, high_low_spread=1.0, close=100.0)
    cfg = PositionSizingConfig(mode="volatility", risk_pct=0.01, atr_multiplier=1.0, min_units=1, max_units=1_000_000)
    units = compute_units(df, balance=10_000, cfg=cfg)
    # risk_amount=100, stop_distance=ATR*1.0=1.0 -> units=100
    assert units == pytest.approx(100, abs=1)


def test_compute_units_rejects_unknown_mode():
    df = _flat_range_df()
    cfg = PositionSizingConfig(mode="not-a-real-mode")
    with pytest.raises(ValueError):
        compute_units(df, balance=10_000, cfg=cfg)
