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
    # max_notional_pct set generously high so neither case clamps against
    # it -- isolates the inverse-ATR-scaling behavior from the notional cap.
    low_vol_units = volatility_based_units(
        balance=10_000, price=100, atr=1.0, risk_pct=0.01, atr_multiplier=1.5, max_notional_pct=1.0
    )
    high_vol_units = volatility_based_units(
        balance=10_000, price=100, atr=10.0, risk_pct=0.01, atr_multiplier=1.5, max_notional_pct=1.0
    )
    assert low_vol_units > high_vol_units


def test_volatility_based_units_respects_notional_bounds():
    # ATR huge relative to balance -> raw calc wants a position smaller
    # than min_notional worth of units, clamped up to the floor.
    tiny_risk = volatility_based_units(
        balance=10_000, price=100, atr=200, risk_pct=0.01, min_notional=50.0, max_notional_pct=0.5
    )
    assert tiny_risk == pytest.approx(0.5)  # 50 / 100 = 0.5 units

    # ATR tiny relative to balance -> raw calc wants a huge position,
    # clamped down to max_notional_pct of balance.
    huge_risk = volatility_based_units(
        balance=10_000, price=100, atr=0.0000001, risk_pct=0.01, min_notional=50.0, max_notional_pct=0.5
    )
    assert huge_risk == pytest.approx(50)  # (10000 * 0.5) / 100 = 50 units


def test_volatility_based_units_scales_correctly_across_wildly_different_prices():
    # Regression test: this is the actual bug found running the bot on
    # BTC-USD -- 1 unit of a $1 asset and 1 unit of a $78,000 asset are not
    # comparable, so bounds must be notional-based, not raw unit counts.
    balance = 10_000.0
    cheap_asset_units = volatility_based_units(
        balance=balance, price=1.10, atr=0.01, risk_pct=0.01, min_notional=50.0, max_notional_pct=0.5
    )
    expensive_asset_units = volatility_based_units(
        balance=balance, price=78_000.0, atr=0.01, risk_pct=0.01, min_notional=50.0, max_notional_pct=0.5
    )

    # Both positions must respect the same dollar cap regardless of the
    # instrument's raw price -- neither should exceed half the balance.
    assert cheap_asset_units * 1.10 <= balance * 0.5 + 1e-6
    assert expensive_asset_units * 78_000.0 <= balance * 0.5 + 1e-6
    # And the expensive asset should get proportionally FEWER units for a
    # comparable notional exposure, not the same raw count.
    assert expensive_asset_units < cheap_asset_units


def test_volatility_based_units_falls_back_to_min_notional_on_bad_atr():
    assert volatility_based_units(balance=10_000, price=100, atr=0) == pytest.approx(0.5)
    assert volatility_based_units(balance=10_000, price=100, atr=None) == pytest.approx(0.5)
    assert volatility_based_units(balance=10_000, price=100, atr=float("nan")) == pytest.approx(0.5)


def test_volatility_based_units_zero_on_invalid_price_or_balance():
    assert volatility_based_units(balance=10_000, price=0, atr=1.0) == 0
    assert volatility_based_units(balance=0, price=100, atr=1.0) == 0


def test_compute_units_fixed_mode_ignores_market_data():
    df = _flat_range_df()
    cfg = PositionSizingConfig(mode="fixed", fixed_units=777)
    assert compute_units(df, balance=10_000, cfg=cfg) == 777


def test_compute_units_volatility_mode_uses_atr_and_price():
    df = _flat_range_df(n=20, high_low_spread=1.0, close=100.0)
    cfg = PositionSizingConfig(mode="volatility", risk_pct=0.01, atr_multiplier=1.0, min_notional=1, max_notional_pct=1.0)
    units = compute_units(df, balance=10_000, cfg=cfg)
    # risk_amount=100, stop_distance=ATR*1.0=1.0 -> raw units=100, well within bounds
    assert units == pytest.approx(100, abs=1)


def test_compute_units_rejects_unknown_mode():
    df = _flat_range_df()
    cfg = PositionSizingConfig(mode="not-a-real-mode")
    with pytest.raises(ValueError):
        compute_units(df, balance=10_000, cfg=cfg)
