import pytest

from optimize.deflated_sharpe import assess_significance, expected_max_sharpe_under_null


def test_benchmark_increases_with_more_trials():
    # searching harder (more trials) raises the bar noise alone can clear
    few = expected_max_sharpe_under_null(n_trials=5, sharpe_std=1.0)
    many = expected_max_sharpe_under_null(n_trials=500, sharpe_std=1.0)
    assert many > few


def test_benchmark_scales_linearly_with_sharpe_std():
    low_var = expected_max_sharpe_under_null(n_trials=50, sharpe_std=0.5)
    high_var = expected_max_sharpe_under_null(n_trials=50, sharpe_std=2.0)
    assert high_var == pytest.approx(low_var * 4)


def test_benchmark_zero_for_degenerate_inputs():
    assert expected_max_sharpe_under_null(n_trials=1, sharpe_std=1.0) == 0.0
    assert expected_max_sharpe_under_null(n_trials=0, sharpe_std=1.0) == 0.0
    assert expected_max_sharpe_under_null(n_trials=50, sharpe_std=0.0) == 0.0
    assert expected_max_sharpe_under_null(n_trials=50, sharpe_std=-1.0) == 0.0


def test_assess_significance_flags_result_indistinguishable_from_noise():
    # 100 trials, all clustered near 0 -- the "best" of them (still small)
    # should NOT clear the noise bar for that much searching.
    sharpes = [0.05 * i for i in range(-50, 50)]  # spread -2.5 to 2.45, std ~1.45
    result = assess_significance(sharpes)
    assert result.n_trials == 100
    assert result.best_sharpe == pytest.approx(2.45)
    # with 100 trials this noisy, the noise benchmark should be comparable
    # to or above the actual best -- i.e. not a free pass
    assert result.expected_max_null > 0


def test_assess_significance_clears_bar_with_few_trials_and_strong_result():
    # only 3 trials, one dramatically better than the noise spread -- should
    # clear the (low, since barely any searching happened) noise bar.
    sharpes = [0.1, -0.1, 3.0]
    result = assess_significance(sharpes)
    assert result.clears_null_bar is True
    assert result.margin > 0


def test_assess_significance_empty_input_does_not_crash():
    result = assess_significance([])
    assert result.n_trials == 0
    assert result.best_sharpe == 0.0
    assert result.expected_max_null == 0.0
    assert result.clears_null_bar is False
