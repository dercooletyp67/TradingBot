import pytest

from optimize.search import param_combinations, walk_forward_folds


def test_walk_forward_folds_are_chronological_and_non_overlapping_test_windows():
    folds = walk_forward_folds(n_bars=1000, n_folds=4)

    assert len(folds) == 4
    for train_slice, test_slice in folds:
        assert train_slice.start == 0
        assert train_slice.stop == test_slice.start  # test starts right where train ends
        assert test_slice.stop > test_slice.start

    # each fold's train window grows (walk-forward, not fixed-window)
    train_ends = [train.stop for train, _ in folds]
    assert train_ends == sorted(train_ends)
    assert len(set(train_ends)) == 4


def test_walk_forward_folds_rejects_too_little_data():
    with pytest.raises(ValueError):
        walk_forward_folds(n_bars=5, n_folds=4)


def test_param_combinations_grid_is_full_cartesian_product():
    grid = {"a": [1, 2], "b": [10, 20, 30]}
    combos = param_combinations(grid, search_mode="grid")

    assert len(combos) == 6
    assert {"a": 1, "b": 10} in combos
    assert {"a": 2, "b": 30} in combos


def test_param_combinations_grid_downsamples_when_max_combos_smaller():
    grid = {"a": [1, 2, 3, 4], "b": [1, 2, 3, 4]}  # 16 combos
    combos = param_combinations(grid, search_mode="grid", max_combos=5, seed=1)

    assert len(combos) == 5
    # no duplicates
    assert len({tuple(sorted(c.items())) for c in combos}) == 5


def test_param_combinations_random_never_exceeds_total_space():
    grid = {"a": [1, 2], "b": [1, 2]}  # only 4 possible combos
    combos = param_combinations(grid, search_mode="random", max_combos=100, seed=1)

    # requesting more than exist should return exactly the full space,
    # not hang forever trying to sample distinct combos that don't exist
    assert len(combos) == 4


def test_param_combinations_random_is_reproducible_with_same_seed():
    grid = {"a": list(range(20)), "b": list(range(20))}
    combos1 = param_combinations(grid, search_mode="random", max_combos=10, seed=42)
    combos2 = param_combinations(grid, search_mode="random", max_combos=10, seed=42)

    assert combos1 == combos2
