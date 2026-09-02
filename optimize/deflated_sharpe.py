"""Corrects for the multiple-testing problem inherent in any parameter
search: if you evaluate N (strategy, params) combinations, the BEST one's
Sharpe ratio is inflated just by having tried N things, even if none of
them have any real skill -- with enough trials, pure noise eventually
produces a good-looking Sharpe by chance alone.

This is Bailey & Lopez de Prado's "expected maximum Sharpe ratio under the
null hypothesis of no skill" (their Deflated Sharpe Ratio work, 2014):
given N trials with Sharpe-ratio standard deviation sigma_SR across them,
E[max Sharpe | no real skill] has a closed form. A candidate's Sharpe only
means something once it clears that benchmark -- otherwise it's
indistinguishable from what pure luck would produce given how much
searching you did.

This doesn't prove a strategy IS skillful, only that its result isn't
explainable by search volume alone -- overfitting to the specific backtest
window, regime-dependence, and plain bad luck are all still live
possibilities even for a result that clears this bar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist, pstdev

EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe_under_null(n_trials: int, sharpe_std: float) -> float:
    """The Sharpe ratio you'd expect the BEST of n_trials independent
    evaluations to show even if every single one had zero real skill --
    pure noise, given enough tries, produces an apparently-good result."""
    if n_trials <= 1 or sharpe_std <= 0:
        return 0.0
    z1 = NormalDist().inv_cdf(1 - 1 / n_trials)
    z2 = NormalDist().inv_cdf(1 - 1 / (n_trials * math.e))
    return sharpe_std * ((1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


@dataclass
class SignificanceAssessment:
    n_trials: int
    sharpe_std: float
    expected_max_null: float
    best_sharpe: float

    @property
    def clears_null_bar(self) -> bool:
        return self.best_sharpe > self.expected_max_null

    @property
    def margin(self) -> float:
        """How far above (positive) or below (negative) the noise
        benchmark the best result sits."""
        return self.best_sharpe - self.expected_max_null


def assess_significance(sharpes: list[float]) -> SignificanceAssessment:
    """sharpes: the out-of-sample Sharpe ratio from EVERY combination
    evaluated in a sweep (not just the winner) -- the whole point is that
    the benchmark depends on how much searching was done."""
    n_trials = len(sharpes)
    sharpe_std = pstdev(sharpes) if n_trials > 1 else 0.0
    best_sharpe = max(sharpes) if sharpes else 0.0
    expected_max_null = expected_max_sharpe_under_null(n_trials, sharpe_std)
    return SignificanceAssessment(
        n_trials=n_trials, sharpe_std=sharpe_std,
        expected_max_null=expected_max_null, best_sharpe=best_sharpe,
    )
