# ADR 0004 — Staff authentication and branch-scoped authorization

**Status:** Development draft, not deployed. Date: 2026-11-23.

## Context

The original V1 API is unauthenticated, suitable only for local testing. The
new real web product must prevent object-level privilege escalation (BOLA),
cross-branch loan modification and spoofed roles.

## Decision

- V1 routes are disabled by default with HTTP 404. Local opt-in requires BOTH
  environment flags LIBRARY_RUNTIME_MODE=local and LIBRARY_ENABLE_UNSAFE_V1=1.
  Any recognized managed-host environment explicitly vetoes the opt-in.
- New staff-only /api/v2 routes require a short-lived RSA (RS256) bearer JWT.
  Verified issuer, audience, subject, expiry, not-before, issued-at and max
  lifetime (300 seconds). Unsigned, mismatched algorithms, unknown key IDs and
  missing JWKS configuration fail closed. Public keys only are in the API.
- The future BFF authenticates users with a managed provider and mints
  audience-specific service tokens. No BFF, private signing key, login flow
  or identity provider integration has been implemented in this change.
- PostgreSQL staff_users and staff_branch_grants store active roles. No
  public provisioning endpoint and no implicit demo grants.
- VIEWER can query a granted branch's catalogue. LIBRARIAN, BRANCH_MANAGER
  and NETWORK_ADMIN can lend and return only at explicitly granted branches.
  NETWORK_ADMIN is not a wildcard bypass.
- Loan details and returns authorize the actual destination branch loaded
  from the database, not a branch supplied by the requester. Unauthorized
  object IDs return 404 to minimize existence disclosure.
- Local idempotency key namespace includes the verified staff subject and
  branch; another user cannot replay the same operation by guessing a key.
- Existing legacy tests opt in to local V1 via pytest configuration; the API
  runtime does not default to enabling V1.
- Staff mappings contain opaque subject identifiers and no personal details.

## Limitations and prerequisites to any public deployment

- The multi-organization isolation contract is still unimplemented; branch
  permission alone does NOT constitute per-tenant isolation.
- Authorization has not yet been integrated into interlibrary V2 transfers.
- An authenticated BFF, cookie/CSRF protection, session revocation, account
  provisioning, audit logs, abuse controls, visitor workspace isolation and
  safe deployment configuration are pending.
- Never expose unauthenticated V1 on a public host or treat a passing CI as a
  production security audit.

## Test expectations

Use ephemeral RSA keys in tests and throwaway PostgreSQL: valid/invalid token
claims, unexpected signing algorithm, cross-branch reads/returns, inactive
identities/grants, viewer write denial, network-admin scope, legacy V1 fail
closed on managed hosts, and per-user idempotency. Test and CI outcomes must
be linked to the tested commit, not asserted in advance.

Research foundations: OWASP API1:2023 BOLA, official FastAPI dependency
documentation and PyJWT 2.x verification/claim validation documentation.
