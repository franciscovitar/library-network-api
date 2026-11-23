# Library Network — implementation log

- Source of truth: `franciscovitar/library-network-api`, baseline `main` `0f583edf3a4d80cb05acc99237d2a432b8302abf`.
- Approved by owner on 2026-11-23: persist product/UX/architecture proposal and begin development on a non-protected branch. No permission for Production deploy, new paid infra, third-party contacts or real patron data.
- PAS verified main: `91468744e483bff467f7016c0a880321486a3628`. Genova route: `software-modernization + IMPROVE`; source status `VERIFIED_ACTIVE` and execution limited to development branch and observed tests.
- Blueprint: [LIBRARY_NETWORK_BLUEPRINT_20261123.md](LIBRARY_NETWORK_BLUEPRINT_20261123.md); visual source: [LIBRARY_NETWORK_VISUAL_CONCEPT_20261123.html](LIBRARY_NETWORK_VISUAL_CONCEPT_20261123.html).
- Original visualization is a static DESIGN CONCEPT containing illustrative data. Never call it a connected live application or test proof.
- Preservation: existing FastAPI/Postgres interlibrary semantics, existing PostgreSQL integration tests and `showcase/` remain intact; only additive, backward-compatible development.
- Environment: library backend not publicly authenticated; do not publish any write-enabled API until authentication/branch authorization and abuse controls pass negative tests.
- First technical objective: preserve the interlibrary domain and implement a bounded operational API vertical slice, with real database tests.
- QA fields: static checks — NOT_RUN; PostgreSQL tests — NOT_RUN until CI; browser E2E — NOT_RUN; deployment — NOT_AUTHORIZED.

## First verified backend checkpoint

- Local circulation code introduced with Alembic `0002` and new real-DB API tests.
- GitHub Actions run [45231705559](https://github.com/franciscovitar/library-network-api/actions/runs/45231705559), commit `c01db4d03dd8be5f26e6703f48f78acbd0bf819b`: **139 passed**, Ruff lint/format PASS, PostgreSQL integration guard PASS. This is a code/CI observation, not a deployment or browser acceptance.
- Catalog search and availability per branch added afterward; must have its own new commit-linked CI result before PASS.
- UI, staff authentication, branch roles, multi-tenant/public sandbox and hosted API remain NOT_IMPLEMENTED / NOT_RUN.

## Catalogue + concurrency checkpoint

- Commit `fba5022cf026576116fa63deb481a1b35c3147c8`: real PostgreSQL catalogue search by title, author and ISBN, per-branch availability, plus state-sensitive integration tests.
- [GitHub Actions #45232252696](https://github.com/franciscovitar/library-network-api/actions/runs/45232252696): **144 passed; 0 failed; 0 skipped; 132 real-PostgreSQL integration and 12 other tests**. Ruff lint/format PASS. No browser or auth claim.
- Added explicit local/interlibrary concurrent race and duplicate-key tests afterward. These are pending their **own** commit-linked CI confirmation; do not generalize the previous 144-test result.
- Current product status: BACKEND_SLICE_IN_DEVELOPMENT; frontend connected to API NOT_IMPLEMENTED; RBAC/tenant/public deployment NOT_AUTHORIZED.
