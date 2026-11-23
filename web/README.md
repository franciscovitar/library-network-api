# Library Network — Operations web (development)

**Status:** Unreleased feature branch. Next.js App Router UI/BFF is being
built on the **real** FastAPI + PostgreSQL backend, not on `showcase/` fixtures.
This does **not** claim public availability or a browser E2E result.

## Architecture and contract

- Public product landing page and protected operator workspace; Spanish UI.
- GitHub OAuth login via Auth.js v5. The JWT session maps the immutable provider
  account ID to `github:<providerAccountId>`, **not** an unverified email or username.
- The BFF signs a new three-minute `RS256` audience token for each upstream
  FastAPI call, with its **server-only** PKCS#8 key; the browser never receives
  these tokens, the API URL, or the signing key.
- FastAPI independently checks the signature against **public** JWKS and
  validates the active `staff_users`/`staff_branch_grants` rows every time.
  OAuth login does NOT create permissions. Privileged users must be explicitly
  provisioned via an approved operator workflow (not yet implemented).
- Staff routes under `/api/v2` only, server actions enforce a real authenticated
  session, and Next.js performs Origin/Host CSRF checks. No arbitrary
  `serverActions.allowedOrigins` overrides.
- Catalogue, copy inventory, member lookup, loan issue/return, dashboard:
  data is fetched from PostgreSQL through FastAPI with `cache: no-store`.
  No localStorage-based loan logic or fake counters.
- The original `showcase/` is legacy evidence only. It is not the default UI.

## Development and safe configuration

1. `cd web && npm install` (Node.js 22 or newer). No external deployment.
2. Copy `.env.example` to an ignored `.env.local`. Supply **your own**
   GitHub OAuth application credentials in local environment **without putting
   them in chat or GitHub**.
3. Backend: apply Alembic migrations, use a **disposable synthetic** PostgreSQL
   database, and set issuer/audience and matching PUBLIC JWKS. Keep
   `LIBRARY_ENABLE_UNSAFE_V1` unset on any hosted environment.
4. A trusted operator must explicitly provision the OAuth subject and branch
   grants in backend DB; no self-registration or anonymous access is supplied.
5. `npm run dev`. `npm run typecheck`, `npm run test` and `npm run build`
   must pass before any Preview exposure. The Python CI suite is separate.

The `LIBRARY_JWT_ISSUER` and `LIBRARY_JWT_AUDIENCE` settings must match
in BFF and backend. `LIBRARY_API_SIGNING_KEY_PKCS8` is NEVER a `NEXT_PUBLIC_*`
variable. The backend must receive only its matching `LIBRARY_JWKS_JSON`.
Never reuse examples as production credentials.

## Release gates not yet met

- OAuth credentials and BFF service-key lifecycle not provisioned/rotated/tested.
- No approved organization/tenant model or visitor-isolated demo workspaces.
- No enrollment/revocation UI, audit log, full rate-limit system or policy
  for protecting real library members' personal data.
- No real-browser QA, accessibility audit, QA deployment, public release or
  real institutional onboarding.
- The interlibrary transfer UI is pending; do not offer a fake button.

For methodology see `../docs/product/LIBRARY_NETWORK_BLUEPRINT_20261123.md`
and `../docs/adr/0004-staff-authorization.md`.
