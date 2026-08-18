import pytest

from data.fetch import generate_synthetic_ohlc


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Redirects storage.db (and live.learn_log) at an isolated temp file/dir
    so tests never touch the real local or cloud state."""
    import storage.db as db
    import live.learn_log as learn_log

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(learn_log, "LEARN_DIR", tmp_path / "learn")
    monkeypatch.setattr(learn_log, "CURRENT_STRATEGY_FILE", tmp_path / "learn" / "current_strategy.json")
    monkeypatch.setattr(learn_log, "HISTORY_FILE", tmp_path / "learn" / "history.jsonl")

    db.init_db()
    return db


@pytest.fixture
def ohlc_df():
    return generate_synthetic_ohlc(n_bars=500, seed=7)
