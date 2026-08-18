import datetime as dt

from live.paper_trader import _resolve_seed, _retune_due
from storage.db import set_bot_status, set_last_retune_at


def test_resolve_seed_uses_cli_seed_on_genuinely_fresh_state(temp_db):
    name, params, is_fresh = _resolve_seed("sma_cross", {"fast": 10, "slow": 50})

    assert name == "sma_cross"
    assert params == {"fast": 10, "slow": 50}
    assert is_fresh is True


def test_resolve_seed_resumes_from_persisted_state_ignoring_cli_seed(temp_db):
    set_bot_status("rsi_reversion", "EUR_USD", '{"period": 21, "oversold": 20, "overbought": 80}', running=True)

    # a restart passing a totally different CLI seed should still resume
    # whatever auto-retune had already settled on, not reset to this.
    name, params, is_fresh = _resolve_seed("sma_cross", {"fast": 10, "slow": 50})

    assert name == "rsi_reversion"
    assert params == {"period": 21, "oversold": 20, "overbought": 80}
    assert is_fresh is False


def test_retune_not_due_when_auto_retune_disabled(temp_db):
    set_last_retune_at(dt.datetime.utcnow().isoformat())
    assert _retune_due(auto_retune_hours=None) is False
    assert _retune_due(auto_retune_hours=0) is False


def test_retune_not_due_before_first_retune_has_ever_happened(temp_db):
    # last_retune_at is None on a genuinely fresh DB -- must not retune
    # immediately on the very first tick, only after a seed has run once.
    assert _retune_due(auto_retune_hours=6) is False


def test_retune_not_due_before_interval_elapses(temp_db):
    set_last_retune_at((dt.datetime.utcnow() - dt.timedelta(hours=3)).isoformat())
    assert _retune_due(auto_retune_hours=6) is False


def test_retune_due_after_interval_elapses(temp_db):
    set_last_retune_at((dt.datetime.utcnow() - dt.timedelta(hours=7)).isoformat())
    assert _retune_due(auto_retune_hours=6) is True
