"""Database connection setup and request-scoped dependencies."""

import os
from functools import lru_cache

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """One engine per process; never share sessions across requests."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return create_engine(database_url, pool_pre_ping=True)


def get_session_factory(engine: Engine = Depends(get_engine)) -> sessionmaker:
    """Factory of short-lived sessions. Each command opens its own via `factory.begin()`:
    one explicit transaction per command; sessions are never shared across requests/threads."""
    return sessionmaker(engine, expire_on_commit=False)
