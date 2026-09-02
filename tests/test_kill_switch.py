import pytest

from live.kill_switch import check_drawdown
from storage.db import get_peak_equity


def test_first_call_sets_peak_to_current_equity(temp_db):
    should_halt, drawdown = check_drawdown(current_equity=10_000.0, max_drawdown_pct=20.0)
    assert should_halt is False
    assert drawdown == pytest.approx(0.0)
    assert get_peak_equity() == pytest.approx(10_000.0)


def test_peak_tracks_new_highs(temp_db):
    check_drawdown(10_000.0, max_drawdown_pct=20.0)
    check_drawdown(12_000.0, max_drawdown_pct=20.0)
    assert get_peak_equity() == pytest.approx(12_000.0)


def test_peak_does_not_fall_when_equity_dips(temp_db):
    check_drawdown(10_000.0, max_drawdown_pct=20.0)
    check_drawdown(12_000.0, max_drawdown_pct=20.0)
    check_drawdown(11_000.0, max_drawdown_pct=20.0)  # dip, still above threshold
    assert get_peak_equity() == pytest.approx(12_000.0)  # peak unchanged


def test_halts_when_drawdown_exceeds_threshold(temp_db):
    check_drawdown(10_000.0, max_drawdown_pct=20.0)  # peak = 10,000
    should_halt, drawdown = check_drawdown(7_500.0, max_drawdown_pct=20.0)  # -25%
    assert should_halt is True
    assert drawdown == pytest.approx(-25.0)


def test_does_not_halt_within_threshold(temp_db):
    check_drawdown(10_000.0, max_drawdown_pct=20.0)
    should_halt, drawdown = check_drawdown(8_500.0, max_drawdown_pct=20.0)  # -15%, within bounds
    assert should_halt is False
    assert drawdown == pytest.approx(-15.0)


def test_disabled_when_max_drawdown_pct_is_none(temp_db):
    check_drawdown(10_000.0, max_drawdown_pct=None)
    should_halt, drawdown = check_drawdown(1_000.0, max_drawdown_pct=None)  # -90%, catastrophic
    assert should_halt is False  # kill switch off -- still just reports the number
    assert drawdown == pytest.approx(-90.0)


def test_peak_still_tracked_even_when_kill_switch_disabled(temp_db):
    # so turning the switch on later measures drawdown from the real peak,
    # not from whatever equity happened to be at that moment.
    check_drawdown(10_000.0, max_drawdown_pct=None)
    check_drawdown(15_000.0, max_drawdown_pct=None)
    assert get_peak_equity() == pytest.approx(15_000.0)
