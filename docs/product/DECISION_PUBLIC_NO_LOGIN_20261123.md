# DECISION — Library Network as a real public product without login

**ID:** LIBRARY-PUBLIC-NO-LOGIN-20261123  
**Date:** 2026-11-23 · Argentina  
**Owner decision:** APPROVED_DIRECTION / PORTFOLIO_RELEASE_IN_PROGRESS (current release status: see PR #7)  
**Repo:** `franciscovitar/library-network-api`, feature PR #4  
**PAS main verified at this decision:** `545aa9def3993be579a333b750739c3558441218`  
**Classification:** PROJECT / product decision, no real library or patron data.

## 1. Owner intent — canonical, overrides previous mandatory-login approach

The owner explicitly clarified in the IA project chat:

> «yo haria todo tal cual venimos haciendo, como una aplicacion real, pero sin login, asi un recluter puede entrar, o sea si le ponemos login no va a poder entrar nadie, yu no cumple su funcion».

**Product acceptance:** A recruiter opens Library Network from the portfolio, immediately enters the **real**, polished product and can use the actual catalogue, checkout, return, branch operations and eventually transfers **without GitHub OAuth, password, account or signup**. The portfolio explains/presents the project, but is **not** the operational product.

`showcase/` (browser-only simulator) is NOT an acceptable replacement, nor are localStorage inventory, fake API responses, decorative cards or changes that disappear without a persisted transaction. The public experience may contain **invented books/members**, but the backend must persist authentic actions in PostgreSQL with transactional invariants.

**Preserve:** existing FastAPI/SQLAlchemy/PostgreSQL domain, local and interlibrary lending, concurrency constraints, idempotency, signed service tokens, staff RBAC, Next.js/React professional UI, existing tests and blueprint. **Change UX priority:** public/guest flow is now the DEFAULT; OAuth-backed staff/admin becomes secondary, not a gate to view/use the product.

## 2. Public guest model (without authentication friction)

- `/demo` (or equivalent) is a one-click *start using* route; **no login prompt**. The BFF issues an opaque, cryptographically unguessable visitor capability and stores it in a `HttpOnly`, `SameSite=Lax`, short-lived cookie (`Secure` on HTTPS). Cookie is not readable by JavaScript and not placed in URL/localStorage.
- Server-side identity is `guest:<random UUID v4>` encoded in a short-lived, audience-scoped, RS256 token signed by BFF only. FastAPI verifies signature, issuer/audience, expiry and subject type. Client cannot choose workspace ID, staff role or branch.
- PostgreSQL owns `demo_workspaces`, workspace branches and workspace member associations. A guest only sees/operates records belonging to **their** workspace. Every read and write resolves workspace ownership from verified token, including loan detail and return by opaque/numeric IDs; API must return 404/403 for a foreign workspace and must not mutate data.
- Seed only **synthetic** data into isolated branch/book/member/copy rows. No cross-workspace shared mutable inventory or real patrons. New visits cannot alter another recruiter's inventory.
- Keep the real transactional loan/return logic with row locks and durable idempotency. Separate keys per guest/workspace. Interlibrary transfer workflow must be scoped to the same workspace before exposing it.
- A signed-out user may still use guest demo. OAuth login, if retained, is only an optional private staff/institutional path; it MUST NOT be mandatory for the recruiter.
- Visitors get clear informational messaging about synthetic data and temporary retention, not “fake simulation.” **No invented screenshot/QA numbers.**

## 3. Security, operating cost and release gates

A public anonymous writable API is high abuse risk. Before *any* public deploy:
1. Real cross-workspace negative tests: guessed branch/copy/member/loan IDs, concurrent guest initialization, replay, expired guest, cross-user read and write, signup absence, cookie tamper.
2. Rate limiting and quotas at both BFF/IP and per-workspace write/creation level, with bounded anonymous session creation; automated abuse tests.
3. Expiration, scheduled cleanup with relational integrity, deletion/retention policy and ability to reset a workspace without leaking other visitors' records. Preserve quota and cost ceilings.
4. Strict CORS, CSRF/origin protections, secure cookies, signing-key rotation; no public V1, no staff endpoint authorization bypass or guest privilege escalation.
5. Safe replay and readback for every high-impact business action; actual PostgreSQL tests and browser E2E. QA Preview on separate isolated infrastructure, no real customers. Test concurrency across tenant boundaries.
6. Confirm hosting, database tenancy, availability, cost, rollback and monitoring; obtain explicit permission for deploy, credentials, external resource writes or fees.

**Current status:** `DRAFT/DEVELOPMENT`; do **not** publicly expose this until the above is met. The decision is about UX, not a grant to publish an unsafe anonymous write API.

## 4. Architecture adaptation with minimum rework

- **Frontend:** reuse `web/` components, dashboard/catalogue/circulation; route public CTA to automatic guest space. A dedicated cookie-backed guest BFF uses the same service-signer building blocks but a different backend guest API namespace; no browsers hold API credentials.
- **Backend:** add an isolated `/api/v2/guest` namespace and database-enforced workspace/branch/member ownership; no guest principals registered as `StaffUser` and no staff grant bypass.
- **Data model:** guest workspace records, own branches and memberships; existing `loans` and `copies` continue to be authoritative with strict per-workspace lookups. Original `/api/v2` staff authorization remains unchanged and private.
- **Development staging:** persist this ADR first; build a bounded workspace + read/checkout/return vertical slice; verify with real PostgreSQL; then BFF cookie flow and browser QA. Only after security gates, decide controlled Preview.

## 5. Relationship to prior architecture

This **supersedes only the UX assumption** in `docs/adr/0005-nextjs-bff-identity.md` and `docs/product/LIBRARY_NETWORK_BLUEPRINT_20261123.md` that staff GitHub OAuth gates the primary product flow. It does not revoke signed server-to-server authentication or staff-specific authorization. Keep the original files for provenance, link this decision prominently in README, implementation log and web docs.

## 6. Sources reviewed

- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP API1:2023 BOLA: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- Next.js cookies / Server Actions: https://nextjs.org/docs/app/api-reference/functions/cookies
- Existing PAS Genova skill and permission policy at recorded canonical SHA; repository code at actual PR commit.

**Definition of Done:** recruiter can enter and perform real, persistent, isolation-safe actions without login; maintainers have evidence-linked automated and browser QA, cost controls and lifecycle cleanup; portfolio links to the functioning product rather than a simulation.


## Portfolio release scope — owner update (2026-11-24)

The owner authorized a public portfolio release using only existing Aiven Free and Render Free services. Remove the temporary Basic Auth gate from the web experience. Any visitor may enter and use the synthetic guest demo without an account, password or signup. This updates the earlier do-not-publish release gate for this bounded portfolio scenario.

The following frictionless safeguards remain in force: a server-only BFF signing key, short-lived signed service tokens, HttpOnly guest capability cookies, verified Origin/Host handling, random per-visitor identities, PostgreSQL-scoped workspaces and existing per-visitor product quotas. The browser receives no database credentials, signing key or staff role. Staff routes still require staff JWT/RBAC.

Accepted limits: no added WAF, external IP-rate-limit provider or new infrastructure; only synthetic records are exposed. This is not a production service. Render cold starts/free quotas and Aiven's free database limits are documented in the [zero-cost hosting guide](../ops/ZERO_COST_HOSTED_QA_20261123.md). No Vercel project, Production deployment, existing library-network-showcase, client environment or billing settings are in scope.
