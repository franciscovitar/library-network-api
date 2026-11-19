"""The demo script stays correct: it runs in-process against the API on real PostgreSQL."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.integration.helpers import counts

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo_scenario.py"


def load_demo():
    spec = importlib.util.spec_from_file_location("demo_scenario", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def in_process_caller():
    """Same contract as the script's HTTP caller; a fresh client per call (thread-safe)."""

    def call(method, path, body=None, headers=None):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.request(method, path, json=body, headers=headers)
        return response.status_code, response.json()

    return call


def transcript(demo, run_id="demo-1"):
    lines: list[str] = []
    demo.run_demo(in_process_caller(), run_id, lines.append)
    return "\n".join(lines)


def test_demo_completes_the_full_cycle(api, app_engine):
    demo = load_demo()
    text = transcript(demo)
    assert text.rstrip().endswith("DEMO OK: complete loan cycle verified")
    # exactly one loan survived the race; two transfers; 4 + 4 history rows; 1 key claim kept
    # for the winner (the loser's claim rolled back) + none for the refused "blocked" request.
    assert counts(app_engine) == {
        "loans": 1,
        "transfers": 2,
        "transfer_events": 8,
        "idempotency_records": 1,
    }


def test_demo_transcript_is_identical_across_fresh_databases(
    api, app_engine, create_database, template_url
):
    """Determinism: two runs on freshly seeded databases print byte-identical transcripts,
    even though which racing request wins is decided by the database at run time."""
    from sqlalchemy import create_engine

    from app.db import get_engine

    demo = load_demo()
    first = transcript(demo)

    second_url = create_database(template=template_url)
    second_engine = create_engine(second_url, pool_size=10, max_overflow=10)
    app.dependency_overrides[get_engine] = lambda: second_engine
    try:
        second = transcript(demo)
    finally:
        app.dependency_overrides[get_engine] = lambda: app_engine
        second_engine.dispose()
    assert first == second
    assert "DEMO OK" in first


def test_reusing_a_run_id_is_refused_before_anything_is_written(api, app_engine):
    demo = load_demo()
    transcript(demo, run_id="same")
    after_first_run = counts(app_engine)
    with pytest.raises(demo.DemoError, match="already used"):
        transcript(demo, run_id="same")
    assert counts(app_engine) == after_first_run  # the refusal left no stray loan behind
    # a new run id works on the same database: the cycle can be repeated
    assert "DEMO OK" in transcript(demo, run_id="other")
    assert counts(app_engine)["loans"] == 2
