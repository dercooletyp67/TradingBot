import pytest

from strategies import STRATEGIES


@pytest.mark.parametrize("name", list(STRATEGIES.keys()))
def test_strategy_signals_are_valid_positions(name, ohlc_df):
    strategy = STRATEGIES[name]
    # use the first value of each param as a lightweight smoke check --
    # full param coverage is optimize/search.py's job (see test_optimize_search.py)
    params = {k: v[0] for k, v in strategy.param_grid.items()}

    signal = strategy.generate_signals(ohlc_df, **params)

    assert len(signal) == len(ohlc_df)
    assert signal.index.equals(ohlc_df.index)
    assert set(signal.unique()).issubset({-1, 0, 1})


@pytest.mark.parametrize("name", list(STRATEGIES.keys()))
def test_strategy_registered_with_nonempty_param_grid(name):
    strategy = STRATEGIES[name]
    assert strategy.param_grid
    for values in strategy.param_grid.values():
        assert len(values) > 1  # a grid of size 1 wouldn't be worth searching
