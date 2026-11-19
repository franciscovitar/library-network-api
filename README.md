# Library Network API

**Status:** Checkpoint A verified by a successful GitHub Actions run; a [draft case study](docs/case-study.md) is ready for review. Academic-source attribution is still pending. This is a **portfolio engineering lab**, not a production or hosted API.

A deliberately bounded Python/FastAPI + PostgreSQL project to demonstrate safe interlibrary lending, transactional domain logic, concurrency, idempotency and verifiable testing.

**Implemented:** the complete interlibrary loan lifecycle over a REST API (request -> outward transfer -> receipt -> activation -> borrower return -> return transfer -> closed), with one database transaction per command, `SELECT ... FOR UPDATE` row locks in a fixed order, `Idempotency-Key` support, the V1.1 relational schema with a reviewed Alembic migration, a deterministic synthetic seed, and integration tests on real PostgreSQL (lifecycle, GOOD/DAMAGED returns, state errors, rollback, concurrency). A deterministic end-to-end demo script and a CI workflow that refuses to pass when the PostgreSQL tests are skipped. **Not implemented:** hosted deployment or authentication. The case study remains a draft until attribution and review are complete. See [Status and Checkpoint A](#status-and-checkpoint-a).

## Quick start: local-only Docker demo

Prerequisite: Docker with Compose.

```bash
docker compose up --build -d      # db -> `alembic upgrade head` (migrate job) -> API
curl http://127.0.0.1:8000/ready
docker compose run --rm api python -m app.persistence.seed   # synthetic demo data (insert-only)
python scripts/demo_scenario.py                              # full loan cycle, asserted step by step
```

Open http://127.0.0.1:8000/docs for Swagger/OpenAPI. The seed refuses to touch a database that already has data ("Seed skipped"). `docker compose down` keeps the database volume; `docker compose down -v` destroys local demo data, run it only intentionally.

The API binds to **127.0.0.1 only** and PostgreSQL publishes **no host port**. Compose credentials are non-secret local demo values. The API is unauthenticated and **not safe to expose publicly**.

## Deterministic demo

[`scripts/demo_scenario.py`](scripts/demo_scenario.py) (standard library only) drives one complete cycle over HTTP and asserts every step: two **simultaneous** requests for one copy (exactly one wins), idempotent replay and key reuse, an illegal transition refused, the outward trip, activation, the borrower's return (the copy stays blocked), the return trip, and the final state (copy `AVAILABLE` at its owner, loan `CLOSED`). It needs the seeded demo data and an unused `--run-id` (a reused one is refused by a side-effect-free pre-check). The transcript omits everything that depends on timing or on which racing request wins, so two runs on freshly seeded databases are byte-identical (checked 3 times over real HTTP against uvicorn, and by a test). Loan ids are not printed because they are reserved before validation, so rejected requests leave gaps in the sequence.

## The lifecycle

```text
Loan      REQUESTED ---activate---> ACTIVE ---return---> RETURNING ---(return transfer RECEIVED)---> CLOSED
Transfer  PREPARED -> DISPATCHED -> IN_TRANSIT -> RECEIVED        (one OUTBOUND + one RETURN per loan)
Copy      AVAILABLE -> RESERVED -> IN_TRANSIT -> RESERVED -> ON_LOAN -> PENDING_RETURN
                    -> IN_TRANSIT -> AVAILABLE | RETIRED
```

| Step | Call | Effect (all in one transaction) |
|---|---|---|
| 1 | `POST /api/v1/loans/interlibrary` + `Idempotency-Key` | loan `REQUESTED`, outward transfer `PREPARED` + initial history, copy `RESERVED` (201; replay 200) |
| 2 | `POST /api/v1/transfers/{id}/transitions` `{"next_status":"DISPATCHED"}` | copy `IN_TRANSIT`, location unchanged |
| 3 | same, `IN_TRANSIT`, then `RECEIVED` | on receipt the copy's location becomes the destination, copy `RESERVED` |
| 4 | `POST /api/v1/loans/{id}/activate` | loan `ACTIVE` (due in 14 days), copy `ON_LOAN`; re-checks the member is enabled |
| 5 | `POST /api/v1/loans/{id}/return` `{"condition":"GOOD"}` or `"DAMAGED"` | loan `RETURNING` (still nonterminal), copy `PENDING_RETURN`, RETURN transfer `PREPARED` |
| 6 | transitions on the return transfer | `DISPATCHED`/`IN_TRANSIT`: copy `IN_TRANSIT`; `RECEIVED`: copy back at its owning branch, `AVAILABLE` (GOOD) or `RETIRED` (DAMAGED), loan `CLOSED` |

Reads: `GET /api/v1/branches`, `/books?limit=&offset=` (max 100), `/copies/{id}`, `/loans/{id}`, `/transfers/{id}` (with history).
Errors are `{"error": {"code": "...", "message": "..."}}`: `404` not found, `409` state or idempotency conflict (`copy_not_available`, `illegal_transition`, `idempotency_key_reuse`, `member_disabled`, ...), `422` `validation_error`, `500` `internal_error` (sanitized).

Example (what was run against the Compose stack, 2026-11-18):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/loans/interlibrary -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-req-001' -d '{"member_id":1,"copy_id":1,"destination_branch_id":2}'
curl -X POST http://127.0.0.1:8000/api/v1/transfers/1/transitions -H 'Content-Type: application/json' \
  -d '{"next_status":"DISPATCHED"}'      # then IN_TRANSIT, RECEIVED
curl -X POST http://127.0.0.1:8000/api/v1/loans/1/activate
curl -X POST http://127.0.0.1:8000/api/v1/loans/1/return -H 'Content-Type: application/json' -d '{"condition":"GOOD"}'
```

## How concurrency and idempotency work

Lock order for every command: **idempotency claim (request only) -> copy -> loan -> transfer**. State is re-read and validated *after* the locks are held.

- **Request:** `INSERT ... ON CONFLICT DO NOTHING` claims `(operation, key)` with a pre-allocated loan id (the FK is deferred, so a claim can never commit without its loan); then `SELECT ... FOR UPDATE` on the copy; validation; writes; commit. A second transaction with the same key waits for the first: after its commit it replays (200), after its rollback it proceeds. A rejected request rolls its claim back, so it does **not** consume the key.
- **Replay** returns the original loan resource (same id) with its *current* state, not a frozen copy of the first response.
- **Other commands** do an unlocked lookup of which copy to lock, then lock copy -> loan -> transfer. A losing concurrent command sees the new state and gets `409` without writing.
- The database constraints (partial unique index, unique history, CHECKs) remain a second line of defence; an unexpected constraint violation is mapped to `409 constraint_conflict`.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m pytest -q                      # unit + HTTP only; integration tests are SKIPPED without a database
                                         # (set REQUIRE_INTEGRATION_TESTS=1 to turn skips into failures, as CI does)
python -m ruff check . && python -m ruff format --check .
```

Integration tests need a **real PostgreSQL** (SQLite is never substituted):

```powershell
docker compose -f compose.test.yaml up -d --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg://library_test:local_test_only@127.0.0.1:55432/postgres"
python -m pytest -q
docker compose -f compose.test.yaml down
```

The tests create uniquely named throwaway databases (`lnapi_test_*`), build the schema with `alembic upgrade head` (not `create_all`) once as a template, clone it per test, and drop only what they created. The demo database is never used. The test engine sets `lock_timeout`, so a deadlock fails a test instead of hanging it. Time is injected (`FakeClock`), never slept.

| Area | What is verified on PostgreSQL |
|---|---|
| Schema | migration up/down/up, no drift vs. models, every constraint by exact name, deferred idempotency FK, DB-level race on the partial unique index |
| Lifecycle | full round trip (GOOD) and DAMAGED return (copy `RETIRED` only on final reception), location changes only on receipt, copy blocked during `RETURNING` and return transit, re-requestable after `CLOSED` |
| State errors | skipped/backward/duplicate transitions, early/duplicate activation, early/duplicate return, disabled member at request and at activation, inactive/same branch, unknown ids, invalid payloads; each rejected call leaves every table unchanged |
| Idempotency | replay (200), same key + different body (409), key order irrelevant, rejected request does not consume the key |
| Rollback | injected failure after rows were written (request, outward transitions, final return reception, return) rolls back loan, copy, transfer, history and key claim together; response is a sanitized 500 |
| Concurrency | different keys, same copy (2 and 5 threads, plus injected scheduler delays): one `201`, rest `409`, one loan/transfer/event/claim; same key + body (2 and 6 threads, plus a delayed winner): one `201`, rest `200` with the same loan id, no duplicates; same key + different bodies; simultaneous advance / receipt / activation / return apply once; a mixed-command stress test on one loan ends consistent with no `500` |

Local results (2026-11-18, Windows 11, Docker Desktop 4.51.0, `postgres:17-alpine`):

- With PostgreSQL, Python 3.14.3: **129 passed** (12 unit/HTTP + 117 integration).
- With PostgreSQL, **in a `python:3.13-slim` container** (same base as the Dockerfile) following the CI steps: install, ruff, pytest, report guard -> **129 passed, 0 skipped**.
- Without `TEST_DATABASE_URL`: 12 passed, 117 **skipped** (skips are not evidence).
- `ruff check` / `ruff format --check`: clean. Concurrency + idempotency/rollback files repeated 5 times: 31/31 passed each time.
- **Mutation checks** (manually removed the implementation, then restored it): without the copy `FOR UPDATE`, the different-keys tests fail; without any row lock, the simultaneous advance/receipt/activation/return tests also fail; ignoring the request hash fails the key-reuse tests; skipping the `AVAILABLE` check fails 9 tests. Honest limit: the mixed-command stress test still passes without locks (database constraints turn the races into `409`s), so it demonstrates freedom from deadlocks and `500`s, not the necessity of the locks.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on **pull requests** only: Ubuntu runner, Python 3.13 (a step fails if it drifts from the Dockerfile's base image), a `postgres:17-alpine` service, `ruff check`, `ruff format --check`, the whole pytest suite, and a report check. Actions are pinned to commit SHAs; permissions are `contents: read`; the database credentials are throwaway CI values.

**CI cannot go green with the PostgreSQL tests skipped**, by two independent guards:

1. `REQUIRE_INTEGRATION_TESTS=1` (set by the workflow): [`tests/conftest.py`](tests/conftest.py) aborts the run (exit 2) if `TEST_DATABASE_URL` is unset or the database is unreachable, and at the end forces a failing exit code if *any* test was skipped or no integration test passed.
2. [`scripts/ci/check_test_report.py`](scripts/ci/check_test_report.py) re-reads the JUnit XML and fails on any failure, **any skip**, or fewer than 100 passed integration tests (a tripwire against the suite shrinking silently; raise it when tests are added).

Both guards were exercised locally before pushing: required-but-no-database (exit 2), unreachable database (exit 2), skips allowed when not required (exit 0), a skipped test with the database present (exit 1 despite no failures), the report check on a report with 114 skips (fails) and on a full run (passes). The workflow was validated by parsing it, checking its structure and pinned SHAs, and emulating its steps in the container above. `actionlint` was **not** run (running it was not permitted in this environment). The result of the real GitHub run is recorded in the PR #1 description and checks, not here, so this file never claims a run it cannot link.

## Data model and decisions

[ADR 0001: relational model](docs/adr/0001-relational-model.md), [ADR 0002: lifecycle, locking and idempotency](docs/adr/0002-lifecycle-locking-idempotency.md). Tables: `branches`, `members`, `books`, `copies`, `loans`, `transfers`, `transfer_events`, `idempotency_records`. The key invariant is one **nonterminal** loan per copy:

```sql
CREATE UNIQUE INDEX uq_loans_copy_id_nonterminal ON loans (copy_id)
  WHERE status IN ('REQUESTED', 'ACTIVE', 'RETURNING');
```

It is both the integrity guard and a small, selective index (closed loans are excluded).

## Status and Checkpoint A

Against the [V1.1 Checkpoint A definition](https://github.com/franciscovitar/personal-ai-system/blob/professional/portfolio-library-network-architecture-20261118/AI/projects/library-network-api/ARCHITECTURE_V1.md):

| Criterion | State |
|---|---|
| API + PostgreSQL + Alembic + synthetic seed | **Met** (verified locally via Compose) |
| One entire outward/return flow | **Met** (API tests and a `curl` run on the Compose stack) |
| Smoke / happy-path tests | **Met** locally on PostgreSQL |
| README with commands | **Met**; the lifecycle diagram above is ASCII, there is no generated diagram |
| OpenAPI | **Met**: `/openapi.json` lists all routes (tested); Swagger UI page not visually checked |
| Runnable without custom frontend or cloud signup | **Met** |
| Reproducible in CI | Workflow defined and locally emulated on Python 3.13; **real run result: see PR #1 checks** (this table is not updated per run) |

Checkpoint B items (not claimed): row locking, constraints, idempotency and concurrent/rollback tests exist, pass locally and are wired into CI; the scripted demo exists. **The case study is drafted but not approved**; academic-source attribution and a documented hosted CI failure case remain pending, so the project must not be presented as finished.

Known limitations: loan ids can have gaps (ids are reserved before validation); CI runs on pull requests only (no push/main trigger, no required-check rule configured); no cancellation or recovery of an abandoned `REQUESTED` loan and no reinstatement of `RETIRED` copies (V1 scope); fixed 14-day loan period, no renewals or fines; unauthenticated local-demo write API; Docker image verified on Docker Desktop for Windows only; `lock_timeout` is set in tests, not enforced in the app engine.

Windows + Docker Desktop crashes on stale sockets: [docs/windows-docker-desktop.md](docs/windows-docker-desktop.md).

## Architecture & boundaries

- [Portfolio case study — draft](docs/case-study.md) (CI evidence linked; attribution still under review)
- [V1.1 architecture contract (PAS draft PR)](https://github.com/franciscovitar/personal-ai-system/blob/professional/portfolio-library-network-architecture-20261118/AI/projects/library-network-api/ARCHITECTURE_V1.md)
- [Project tracking and verifiable milestones (Notion)](https://app.notion.com/p/41c086274b6f81528248e6395f51ad66)
- [Original academic source, preserved separately (tp-DAO)](https://github.com/franciscovitar/tp-DAO)

The application follows the same *domain scenario* as the academic project but does not copy its implementation. Verify collaborators' authorship/permissions before any literal source reuse.

Layout: `app/api` (routes, schemas, errors) -> `app/application` (one use case per command, locking) -> `app/domain` (states, pure rules, errors) -> `app/persistence` (models, queries, seed); `alembic/`; `tests/{unit,integration}`.

Next: review academic-source attribution and the draft case study; document a CI failure case without using hosted runners for iterative diagnosis. Explicit V1 exclusions: new UI, auth SaaS, external library integrations, broad reporting/CRUD, Node rewrite, cloud deployment and production-readiness claims.
