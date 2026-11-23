# Library Network — real operations web (feature branch)

**Status:** GitHub PR #4 · implementation in development, **NOT PUBLICLY DEPLOYED**.  
**Canonical decision:** [public access without login](../docs/product/DECISION_PUBLIC_NO_LOGIN_20261123.md).  
**Release and merge status:** [inspectable gates](../docs/ops/RELEASE_READINESS_20261123.md).

This is the real application built on FastAPI + PostgreSQL, **not** the old
`showcase/` model. Recruiters do not register or log in.

## What works in local browser CI

- Root `/` offers a one-click `Explorar la biblioteca sin registrarte`
  experience. The BFF generates a random UUIDv4, HMAC-signs a short-lived
  HttpOnly + SameSite=Lax cookie and issues a separate, three-minute RS256
  service token only to FastAPI. Secure/__Host cookies activate on HTTPS.
- `/demo` resolves each visitor's PostgreSQL workspace and its own two
  branches, members and inventory. The browser never holds the RSA key,
  the API bearer token or a staff grant.
- `/demo/[branchId]` displays database-backed catalogue, statistics,
  local checkout and return (transacted, with copy locks and idempotency).
- `/demo/[branchId]/transfers` lets the visitor request an interlibrary
  loan, advance the outward transfer PREPARED → DISPATCHED → IN_TRANSIT →
  RECEIVED, activate the loan, register the borrower's return and complete
  the return transfer. The same original PostgreSQL lifecycle remains
  authoritative; all foreign IDs fail object-level authorization.
- Auth.js / GitHub OAuth is retained in `/login` as optional institutional
  staff functionality, **not** required to use the public product. A GitHub
  identity alone never grants a branch role.

## Verification already observed

- [Backend CI #45254202481](https://github.com/franciscovitar/library-network-api/actions/runs/45254202481):
  183 passing tests with 160 PostgreSQL integrations, at
  `1d58206713263728f0e246d97d3e7dc260e4809c`.
- [Web CI #45254202098](https://github.com/franciscovitar/library-network-api/actions/runs/45254202098):
  TypeScript, native tests and Next.js build PASS, same commit.
- [Chromium E2E #45254202312](https://github.com/franciscovitar/library-network-api/actions/runs/45254202312):
  2 real browser tests PASS (local circulation + full interlibrary flow),
  using disposable PostgreSQL 17 and synthetic service keys, same commit.
- Any subsequent commit needs its own new CI readback. Those results do
  **not** establish production/HTTPS deployment, rate-limit effectiveness
  or real institutional readiness.

## Development without real user credentials

1. Node.js 22+, `cd web && npm ci`. No `NEXT_PUBLIC_*` secrets.
2. Backend: disposable PostgreSQL and Alembic migrations; see repository
   `README.md`. Keep unsafe V1 access disabled outside disposable local tests.
3. Set backend `LIBRARY_JWKS_JSON` public key plus issuer/audience and
   BFF `LIBRARY_API_SIGNING_KEY_PKCS8` private key + matching kid in
   ignored local environment. Also set a **separate**
   `LIBRARY_GUEST_COOKIE_SECRET` (>=32 unpredictable characters),
   `LIBRARY_API_URL` (HTTPS in production), issuer and audience.
   Never copy credentials from CI or commit/paste keys into conversations.
4. Run `npm run dev`, `npm run typecheck`, `npm run test`,
   `npm run build`. Browser E2E runs separately under `qa/browser/`.
5. GitHub OAuth client credentials are optional and only necessary when
   explicitly testing the private staff path.

## Blockers before public release

- **Abuse:** global PostgreSQL caps currently allow 60 new guest spaces/hr,
  300 active, 25 loans per workspace; trusted-edge/IP/bot limiting and
  budget/cost review are still outstanding. WAF billable features need approval.
- **Retention:** the cleanup CLI is implemented, transactional and dry-run by
  default; a safe **automatic scheduler is NOT yet connected**. Guests' access
  expires after 24h, but data removal requires the cleanup job.
- **Platform:** actual HTTPS, key management/rotation, hosted Python API and
  PostgreSQL, monitoring, accessibility/mobile checks, guest reset and
  Production hardening need a separate, authorized QA environment.
- **Merge:** the old `library-network-showcase` has an explicit Git auto-deploy veto for `main`, plus an observed branch-skip probe and passing safety CI. Before merging, recheck all exact-head tests and the project settings; the real app remains NOT DEPLOYED.

Sources: [ADR 0005](../docs/adr/0005-nextjs-bff-identity.md),
[ADR 0006](../docs/adr/0006-guest-isolation.md), product blueprint and
the original GitHub Actions checks. Tests are not proof of a public release.
