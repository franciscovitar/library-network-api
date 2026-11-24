"""Keep a single API process compatible with small PostgreSQL connection limits."""

from sqlalchemy.pool import QueuePool

from app.db import get_engine


def test_engine_uses_bounded_connection_pool(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'pool.sqlite'}")
    get_engine.cache_clear()
    engine = get_engine()
    try:
        assert isinstance(engine.pool, QueuePool)
        assert engine.pool.size() == 2
        assert engine.pool._max_overflow == 1
        assert engine.pool.timeout() == 5
        assert get_engine() is engine
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1
    finally:
        engine.dispose()
        get_engine.cache_clear()
