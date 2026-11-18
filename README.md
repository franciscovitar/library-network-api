# Library Network API

**Status:** early backend scaffold (Checkpoint A in progress). This is a **portfolio engineering lab**, not a production or hosted API.

A deliberately bounded Python/FastAPI + PostgreSQL project to demonstrate safe interlibrary lending, transactional domain logic, concurrency, idempotency and verifiable testing.

**Implemented so far:** HTTP liveness/readiness, the **V1.1 relational schema with a reviewed Alembic migration**, a deterministic **synthetic seed**, and **integration tests against real PostgreSQL**. **Not implemented yet:** lending workflows (request/transfer/activate/return), application-level row locking and idempotency logic, read endpoints, CI. See [Status and limitations](#status-and-limitations).

## Quick start — local-only Docker demo

Prerequisite: Docker with Compose.

```bash
docker compose up --build -d      # starts db, runs `alembic upgrade head` (migrate), then the API
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
docker compose run --rm api python -m app.persistence.seed   # optional synthetic demo data
```

The seed is insert-only: on a database that already has data it prints "Seed skipped" and changes nothing.

Open http://127.0.0.1:8000/docs for interactive OpenAPI/Swagger. Expected responses: `{"status":"ok"}` and `{"status":"ready"}`, respectively, when the database is reachable.

To stop containers without deleting the database volume: `docker compose down`. Deleting the named volume destroys local demo data; only run `docker compose down -v` intentionally.

The API binds to **127.0.0.1 only**, and PostgreSQL has **no host-published port**. Compose credentials are deliberately non-secret **local demo values**; never reuse them for a deployment. This is currently an unauthenticated local-only proof of concept, **not safe to expose publicly**.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m pytest -q                      # 4 unit/HTTP tests; integration tests are SKIPPED without a database
python -m ruff check . && python -m ruff format --check .
```

Integration tests need a **real PostgreSQL** (SQLite is never substituted). Start the disposable test
database (127.0.0.1:55432, data in tmpfs) and point the tests at it:

```powershell
docker compose -f compose.test.yaml up -d --wait
$env:TEST_DATABASE_URL = "postgresql+psycopg://library_test:local_test_only@127.0.0.1:55432/postgres"
python -m pytest -q
docker compose -f compose.test.yaml down
```

Each test module creates uniquely named throwaway databases (`lnapi_test_*`), builds the schema with
`alembic upgrade head` (not `create_all`) and drops only what it created. The demo database is never used.

What the integration tests cover: migration up/down/up and **no drift between migration and models**;
every CHECK / UNIQUE / FK / partial-unique-index constraint, identified by exact constraint name; the
claim-before-resource idempotency design (deferred FK); two real connections racing on the same copy
(the database index admits a single winner); the seed (deterministic, idempotent, refuses non-empty
databases, sequences advance); `/ready` against PostgreSQL and when it is unreachable.

Last verified run (2026-11-18, Windows, Docker Desktop 4.51.0, `postgres:17-alpine`, Python 3.14.3):
**63 passed** (4 unit/HTTP + 59 integration), ruff clean.

## Data model and decisions

See [docs/adr/0001-relational-model.md](docs/adr/0001-relational-model.md). Schema summary: `branches`,
`members`, `books`, `copies`, `loans`, `transfers`, `transfer_events`, `idempotency_records`. The key
invariant: at most one **nonterminal** loan (`REQUESTED`, `ACTIVE`, `RETURNING`) per copy, enforced by

```sql
CREATE UNIQUE INDEX uq_loans_copy_id_nonterminal ON loans (copy_id)
  WHERE status IN ('REQUESTED', 'ACTIVE', 'RETURNING');
```

The index is both the integrity guard and a small, selective lookup structure (closed loans are excluded).

## Status and limitations

- No lending flow yet: nothing creates loans/transfers through the API; the schema only guarantees
  that whatever does so cannot violate the invariants. Row locking (`SELECT ... FOR UPDATE`) and the
  idempotency flow belong to the next milestone.
- No GitHub Actions CI yet; evidence above is from a local run.
- The API has no authentication and is local-demo only.
- Windows + Docker Desktop crash on stale sockets: see [docs/windows-docker-desktop.md](docs/windows-docker-desktop.md).

## Architecture & boundaries

- [V1.1 architecture contract (PAS draft PR)](https://github.com/franciscovitar/personal-ai-system/blob/professional/portfolio-library-network-architecture-20261118/AI/projects/library-network-api/ARCHITECTURE_V1.md)
- [Project tracking and verifiable milestones (Notion)](https://app.notion.com/p/41c086274b6f81528248e6395f51ad66)
- [Original academic source, preserved separately (tp-DAO)](https://github.com/franciscovitar/tp-DAO)

The new application follows the same *domain scenario* as the academic project, but does not copy its existing implementation. Verify collaborators' authorship/permissions before any literal source reuse.

Planned sequential deliverables:
1. ~~PostgreSQL schema + reviewed Alembic migration + synthetic seed~~ (done) and a complete transfer/loan lifecycle (next).
2. PostgreSQL row-locking, partial unique constraints, idempotency, rollback tests and CI.
3. Reproducible public case study with truthful proof, not another frontend.

Explicit V1 exclusions: new UI, auth SaaS, external library integrations, broad reporting/CRUD, Node rewrite, cloud deployment and production-readiness claims.
