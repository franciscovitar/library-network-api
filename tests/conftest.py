"""Test-session guard: CI must never go green with the PostgreSQL tests silently skipped.

Locally the integration tests skip when TEST_DATABASE_URL is unset (a convenience). In CI the
environment variable REQUIRE_INTEGRATION_TESTS=1 turns that convenience into a hard failure:

1. at session start, a missing or unreachable database aborts the run (exit code 2);
2. at session end, any skipped test, or zero passed integration tests, forces a failing exit
   code even if every executed test passed.

`scripts/ci/check_test_report.py` re-checks the JUnit report independently of this hook.
"""

from __future__ import annotations

import os
import time

import pytest

REQUIRE_ENV = "REQUIRE_INTEGRATION_TESTS"


def _required() -> bool:
    return os.getenv(REQUIRE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _wait_for_database(url: str, seconds: float = 30.0) -> str | None:
    """Return None when the server answers `SELECT 1`, else the last error."""
    from sqlalchemy import create_engine, text

    engine = create_engine(url, connect_args={"connect_timeout": 3})
    last = "no attempt"
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return None
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                last = f"{type(exc).__name__}: {exc}".splitlines()[0]
                time.sleep(1)
    finally:
        engine.dispose()
    return last


def pytest_sessionstart(session: pytest.Session) -> None:
    if not _required():
        return
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.exit(
            f"{REQUIRE_ENV}=1 but TEST_DATABASE_URL is not set: refusing to run without the "
            "real-PostgreSQL integration tests.",
            returncode=2,
        )
    error = _wait_for_database(url)
    if error:
        pytest.exit(
            f"{REQUIRE_ENV}=1 but PostgreSQL is unreachable via TEST_DATABASE_URL ({error}).",
            returncode=2,
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _required():
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    skipped = reporter.stats.get("skipped", [])
    integration_passed = [
        r for r in reporter.stats.get("passed", []) if "tests/integration/" in r.nodeid
    ]
    problems = []
    if skipped:
        problems.append(f"{len(skipped)} test(s) were skipped")
    if not integration_passed:
        problems.append("no integration test passed")
    if problems:
        reporter.write_line(f"{REQUIRE_ENV}: FAILING the run: {'; '.join(problems)}.", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
