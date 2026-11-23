# Browser E2E: no-login, actual persistence

Playwright Chromium test with a real ephemeral PostgreSQL 17, FastAPI and Next.js
process on **GitHub Actions only**. No Vercel deployment and no real credentials.

The test must visit the recruiter landing, open an anonymous workspace without
login, issue a real loan, observe the PostgreSQL-backed active-loan count,
open a second independent browser, verify isolation, return the first loan,
verify persistence after reload, and reject a tampered session cookie.

The CI job generates its own RSA keypair and exposes ONLY the public JWKS to
FastAPI. All tokens and keys are disposable CI-only and should never be
copied to hosting credentials or GitHub project documentation.

- `npm ci` in the `web/` and `qa/browser/` subprojects.
- Browser dependency pinned to `@playwright/test@1.65.1` in a committed, reproducible `package-lock.json` (`npm ci`).
- The Next.js process runs in **development** mode to allow loopback HTTP to
  FastAPI, so this does not prove deployed Production auth/cookie behavior.
- Playwright test pass proves one browser-mediated vertical path, **not**
  complete accessibility, mobile, security or deployment readiness.
