# ADR 0006 — Public no-login guest session and isolated synthetic workspaces

**State:** IMPLEMENTED_IN_DEV / QA_PARTIAL / PUBLIC_DEPLOYMENT_BLOCKED  
**Decision authority:** Owner's IA conversation 2026-11-23; [canonical product decision](../product/DECISION_PUBLIC_NO_LOGIN_20261123.md).

## Accepted architecture

Browser -> one-click POST Next.js Server Action -> random UUIDv4 -> signed HttpOnly
same-site cookie + BFF-issued short-lived RS256 bearer -> FastAPI guest namespace ->
PostgreSQL `demo_workspaces` + synthetic member/branch associations -> existing
SQLAlchemy circulation functions and unique copy nonterminal-loan constraint.

The browser has **no username/password/GitHub login** and cannot select a staff
role or privileged subject. The BFF holds both HMAC secret and RSA private key.
The API holds only public JWKS and checks signed subject on every request.

## Data and cross-workspace boundaries

- Workspace subject is server-issued `guest:<UUIDv4>`. Creation is serialized
  with a transaction-scoped PostgreSQL advisory lock for idempotent concurrent
  starts. Expired workspaces do not silently reactivate.
- Every branch and synthetic member has a unique workspace association.
  Guest endpoints always resolve the workspace from the verified subject
  and authorize branch/member/copy/loan ownership before reading or mutating.
- Catalogue is filtered by *actual copies* in the requested owned branch,
  never a global book inventory. Loan/copy IDs of another visitor return 404.
- Each guest's local loans reuse the existing row locks, uniqueness constraint,
  idempotency key and PostgreSQL transactions. New loan keys are prefixed
  with the verified guest subject and branch; 25 new loans per workspace.
- Two independent synthetic branches are created per workspace; the guest
  interlibrary transfer UI is **not yet implemented or authorized**.
- The previous staff OAuth+RBAC path is retained but not required for guest entry.

## Evidence and gaps

Real PostgreSQL tests at [CI #45246353465](https://github.com/franciscovitar/library-network-api/actions/runs/45246353465)
verified two independent guests, foreign branch/member/copy/loan rejection,
replay behavior, expiry and loan quota: 174 tests passed in total.
[Web CI #45246892532](https://github.com/franciscovitar/library-network-api/actions/runs/45246892532)
built no-login Next.js BFF/UI and ran local pure capability tests. No live
browser login/session persistence or Preview deployed; synthetic test fixtures
are not proof of real-world security.

**Mandatory before public Preview/Production:** distributed/IP rate limiting,
storage quotas and abuse guard for guest creation, automatic TTL cleanup with
foreign-key-safe readback, guest reset and accessibility/browser E2E, cookie
lifecycle and CSRF tests, secrets/key rotation and budgets. A 24-hour access
expiry alone is NOT deletion of guest data. No production resource authorized.

Research: OWASP Session Management Cheat Sheet; OWASP API1 BOLA (2023);
Next.js Server Actions/cookies official docs. Compare with prior ADR 0005;
this ADR supersedes only mandatory staff login for the recruiter-facing UI.
