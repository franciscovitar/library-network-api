# Library Network API

**Status:** early backend scaffold (Checkpoint A in progress). This is a **portfolio engineering lab**, not a production or hosted API.

A deliberately bounded Python/FastAPI + PostgreSQL project to demonstrate safe interlibrary lending, transactional domain logic, concurrency, idempotency and verifiable testing. The current branch only implements HTTP liveness/readiness checks and the local infrastructure scaffold; **lending workflows, schema migrations and PostgreSQL integration tests are not yet implemented**.

## Quick start — local-only Docker demo

Prerequisite: Docker with Compose.

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Open http://127.0.0.1:8000/docs for interactive OpenAPI/Swagger. Expected responses: `{"status":"ok"}` and `{"status":"ready"}`, respectively, when the database is reachable.

To stop containers without deleting the database volume: `docker compose down`. Deleting the named volume destroys local demo data; only run `docker compose down -v` intentionally.

The API binds to **127.0.0.1 only**, and PostgreSQL has **no host-published port**. Compose credentials are deliberately non-secret **local demo values**; never reuse them for a deployment. This is currently an unauthenticated local-only proof of concept, **not safe to expose publicly**.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Foundation tests cover HTTP liveness, simulated database readiness/failure and OpenAPI shape. The readiness tests use an injected in-memory SQLite engine so they do **not** constitute PostgreSQL integration or concurrency evidence. Real Postgres migrations and integration tests are next.

## Architecture & boundaries

- [V1.1 architecture contract (PAS draft PR)](https://github.com/franciscovitar/personal-ai-system/blob/professional/portfolio-library-network-architecture-20261118/AI/projects/library-network-api/ARCHITECTURE_V1.md)
- [Project tracking and verifiable milestones (Notion)](https://app.notion.com/p/41c086274b6f81528248e6395f51ad66)
- [Original academic source, preserved separately (tp-DAO)](https://github.com/franciscovitar/tp-DAO)

The new application follows the same *domain scenario* as the academic project, but does not copy its existing implementation. Verify collaborators' authorship/permissions before any literal source reuse.

Planned sequential deliverables:
1. PostgreSQL schema + reviewed Alembic migration + synthetic seed and a complete transfer/loan lifecycle.
2. PostgreSQL row-locking, partial unique constraints, idempotency, rollback tests and CI.
3. Reproducible public case study with truthful proof, not another frontend.

Explicit V1 exclusions: new UI, auth SaaS, external library integrations, broad reporting/CRUD, Node rewrite, cloud deployment and production-readiness claims.
