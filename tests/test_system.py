"""Foundation HTTP contract tests; no PostgreSQL concurrency claims yet."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from app.db import get_engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_health_is_independent_of_database():
    assert client.get("/health").json() == {"status": "ok"}


def test_readiness_checks_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        response = client.get("/ready")
    finally:
        engine.dispose()
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_unavailable_database_returns_503():
    class UnavailableEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("offline"))

    app.dependency_overrides[get_engine] = lambda: UnavailableEngine()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}


def test_openapi_describes_current_endpoints():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
    assert "/ready" in response.json()["paths"]
