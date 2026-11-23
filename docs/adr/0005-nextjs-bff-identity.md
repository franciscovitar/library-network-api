# ADR 0005 — Next.js operational web + OAuth identity mapped to API staff grants

**Status:** PROVISIONALLY ADOPTED on development branch, 2026-11-23.
**Deploy authority:** NONE. **Runtime OAuth verification:** NOT_RUN.

## Problem

The former public `showcase/` stored simulated activity in browser state.
A real staff product must render PostgreSQL data and execute issuance, returns
and branch metrics through the existing FastAPI transactional cases, while
the browser cannot steal private service credentials or grant itself a role.

## Decision

- A separate `web/` Next.js 16.4.6 / React 19.3.1 / TypeScript workspace
  renders server-side operational pages and POST Server Actions.
- Auth.js `next-auth@5.0.0-beta.32` GitHub OAuth provider is an **initial**
  identity source (not a definitive institutional login provider). Immutable
  GitHub account ID maps to `github:<providerAccountId>`, never email/display name.
- GitHub login alone does not create a staff grant. FastAPI checks PostgreSQL
  `staff_users`, active `staff_branch_grants`, active branches and permissions
  on every requested resource and mutation.
- On each API call the BFF mints an **RS256 token valid for three minutes**
  with configured issuer, audience, `sub` and `kid`. Signing PKCS#8 material
  is server-only; FastAPI receives the matching public RSA JWKS. API calls use
  `no-store`, bounded timeouts and no cross-origin redirects.
- Mutations use Next Server Actions with Next.js Origin/Host CSRF checks
  and server-side revalidation. The backend is authoritative for idempotency,
  concurrency and state. No client-side fake inventory decrement.
- The operational catalogue and loans are authenticated; an unauthenticated
  recruiter visitor has **no staff role**. Guest demos require separate future
  workspaces with strict data isolation and cleanup.
- Dependencies are pinned in `web/package-lock.json`; CI runs `npm ci`,
  tests, TypeScript and production build. The Python/PostgreSQL CI remains
  independent.

## Alternatives and why not adopted immediately

- Google OAuth: a good candidate for real institutions, but requires approved
  provider identity mapping and configuration; provider choice should be
  evaluated when onboarding actual libraries.
- Custom username/password: would create additional credential handling and
  attack surface; not needed for this first private staff slice.
- Direct browser-to-FastAPI JWT: would leak service bearer material and expand
  CORS/CSRF/authorization surface; rejected.
- Public auto-provisioning of a global synthetic library: cross-visitor
  contamination, unsafe load and data ownership ambiguity; rejected.

## Limitations / no certification

- OAuth/App secret configuration and the Auth.js **beta runtime login flow**
  have not been exercised with a real GitHub OAuth application. This is
  build-tested code, not a live verified OAuth session.
- RSA signing key creation/rotation and issuer/JWKS matching are an operations
  prerequisite, not provided with production credentials.
- `Member` currently represents synthetic codes without branch or organization
  membership; exact lookup must **not** serve real member data before tenant
  scoping is designed and tested.
- Browser session, responsive and accessibility E2E, abuse controls, audit
  trail, tenant isolation and visitor workspaces remain NOT_TESTED/NOT_BUILT.
- The PR remains draft, `main` and Production untouched.

## Sources / evidence

- Next.js authentication and DAL: https://nextjs.org/docs/app/guides/authentication
- Next.js Server Action Origin/Host checks: https://nextjs.org/docs/app/guides/data-security
- Auth.js OAuth and client sign-in: https://authjs.dev/getting-started/session-management/login
- Auth.js session handling: https://authjs.dev/getting-started/session-management/get-session
- JOSE key import and JWT signing: https://github.com/panva/jose
- OWASP Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- Code and commit-linked CI: ../product/IMPLEMENTATION_LOG_20261123.md
