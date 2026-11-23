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
- Added explicit local/interlibrary concurrent race and duplicate-key tests afterward. These are now confirmed by the final commit-linked [GitHub Actions #45232625003](https://github.com/franciscovitar/library-network-api/actions/runs/45232625003): **146 tests passed, 0 failed, 0 skipped; 134 PostgreSQL integration and 12 unit/HTTP**. Ruff lint/format and mandatory real-DB guard passed. The 144-test result applies only to the earlier catalogue commit.
- Current product status: BACKEND_SLICE_IN_DEVELOPMENT; frontend connected to API NOT_IMPLEMENTED; RBAC/tenant/public deployment NOT_AUTHORIZED.

## End-of-block status (2026-11-23)

- Product blueprint and HTML concept persisted unmodified in `docs/product/` on this branch; user-approved direction.
- Development adds local circulation, live catalog search and branch availability, durable idempotency, and concurrent race regression tests. End-to-end **browser app is NOT built**.
- Observed CI at commit `2a865202190633eb9d83c2825ded51d6565318c0`: 146 PASS, PostgreSQL 17, no skips.
- This log-only follow-up does not change executed behavior; any new head commit requires its own CI status to claim latest-head green.
- No merge to `main`, no public API, no credentials or production resources modified by this development block.

## Staff access development — 2026-11-23

- Added `app/security.py`: fail-closed RS256 verifier with fixed issuer/audience, five-minute maximum lifetime, public RSA JWKS and no role trust in browser-provided headers.
- Added PostgreSQL migration `0003_staff_branch_permissions.py`, models for `staff_users` and `staff_branch_grants` and staff-only `/api/v2` catalogue, profile, local loan and return routes.
- Original unauthenticated `/api/v1` is disabled by default and vetoed on recognized managed hosts. Existing CI V1 tests explicitly opt into local mode, not an application default.
- New tests cover anonymous access, role revocation, cross-branch data/object boundaries, duplicate-key namespace separation, cryptographic invalid tokens and no network-admin wildcard bypass.
- [GitHub Actions #45235991498](https://github.com/franciscovitar/library-network-api/actions/runs/45235991498), commit `ae3c132f7dfc59f20810537b53e0bed8a5c71fa8`: **166 PASS; 0 FAIL; 0 SKIP; 143 PostgreSQL integrations + 23 unit/HTTP.** Ruff lint/format PASS.
- Added a later signed-token → FastAPI → PostgreSQL checkout and return E2E integration test; latest-head CI result must be rechecked after this documentation commit.
- Not implemented: Next.js BFF/OAuth login, key management, admin provisioning workflows, audit trails, per-visitor synthetic workspace, organization isolation, browser QA, Production deployment. **API must remain unexposed.**
- This block does not authorize production secrets, paid infrastructure or merge to main.

## Authenticated branch dashboard — 2026-11-23

- Added staff-scoped `GET /api/v2/branches/{branch_id}/overview` returning PostgreSQL-backed counts for total/available copies, distinct titles, active/overdue loans, returns and incoming/outgoing transfers.
- One SQL statement gives all counts a consistent MVCC snapshot; no counters are browser-simulated or extracted from real patron PII.
- Negative QA: grant restrictions and revoked access; operational QA: issue local, return and request interlibrary transfer and see the counts change.
- Verified at code commit `d0702abfaaa31d930fb6d686e66e81eb96d6f425`: [GitHub Actions #45237617852](https://github.com/franciscovitar/library-network-api/actions/runs/45237617852), **169 passed, 0 failed, 0 skipped (146 real PostgreSQL integrations + 23 other)**. Lint/format PASS.
- The prior 167-test run [#45236710232](https://github.com/franciscovitar/library-network-api/actions/runs/45236710232) also passed after adding a signed JWT→API→Postgres issue/return case.
- This log commit also lengthens a synthetic HS256 rejection-test key to remove an avoidable PyJWT warning. CI for the new HEAD must be observed separately.
- Remaining release gates: real Next.js/BFF sign-in and RSA key management, branch provisioning workflow, organizational/visitor demo isolation, audit and abuse controls, browser E2E and an approved QA deployment. **DO NOT DEPLOY the current server publicly.**

## Next.js operations web: first vertical UI (2026-11-23)

- `web/` contains a Next.js 16 App Router/React 19 TypeScript application separate from `showcase/`, with the approved forest-green editorial UX tokens, responsive sidebar, catalogue, operational metrics and real issue/return forms.
- An Auth.js GitHub OAuth identity is mapped to immutable `github:<providerAccountId>`. No automatic staff or branch provisioning. Staff API authorizes every request against PostgreSQL; BFF signs a fresh three-minute RS256 service token with a server-only private key and does not expose it to the browser.
- New secured `/api/v2/branches/{branch_id}/copies` and exact `members/lookup` provide real records for checkout selection, without user-entered database IDs as the primary search interaction.
- Server Actions reverify session before each write; FastAPI enforces grants and physical-copy locks. No client-side state changes are treated as an authorized loan.
- Frontend `package-lock.json` was generated via GitHub Actions and committed; CI uses `npm ci`, TypeScript, native Node tests and `next build`.
- **Observed QA checkpoint** at commit `51e5723adb5149d8dbd4476b222ea755df6936d6`: [Web CI #45241737637](https://github.com/franciscovitar/library-network-api/actions/runs/45241737637) succeeded (npm ci, 3 Node validation tests, TypeScript and production Next build); [Python CI #45241737626](https://github.com/franciscovitar/library-network-api/actions/runs/45241737626) succeeded (PostgreSQL integration suite + Ruff).
- Post-checkpoint UX polish added logout on mobile and on unprovisioned accounts and hides issue links from read-only staff. These changes require their own final CI readback.
- Public OAuth integration has **NOT** been operated with real credentials; BFF-to-FastAPI browser E2E **NOT_RUN**. Dedicated demo workspace per visitor, organization isolation, audit, rate-limiting, access provisioning and deployment **NOT_DONE**. No statement of usability as a publicly deployed product.
