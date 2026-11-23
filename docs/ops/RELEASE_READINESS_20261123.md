# Library Network — Release and merge gates (2026-11-23)

**Scope:** PR #4, `feat/library-network-product-foundation-20261123` — engineering draft.  
**Canonical product decision:** [public, real, without login](../product/DECISION_PUBLIC_NO_LOGIN_20261123.md).  
**PAS reference:** `franciscovitar/personal-ai-system`, main `545aa9def3993be579a333b750739c3558441218`.  
**Execution authority for deployment / external cost:** NONE. **Do not treat test success as production readiness.**

## Independently observed checkpoints

| Dimension | Evidence | Scope |
|---|---|---|
| PostgreSQL transactions, guest isolation, interlibrary and idempotency | [CI #45254202481](https://github.com/franciscovitar/library-network-api/actions/runs/45254202481) — 183 passed, 0 failed, 0 skipped (160 real DB integrations + 23 unit/HTTP), commit `1d58206713263728f0e246d97d3e7dc260e4809c` | Real disposable PostgreSQL 17; not public hosting |
| Frontend compilation and TypeScript | [Web CI #45254202098](https://github.com/franciscovitar/library-network-api/actions/runs/45254202098) SUCCESS, same commit | Next.js production build and static/type validation |
| Recruiter no-login journey | [Browser CI #45254202312](https://github.com/franciscovitar/library-network-api/actions/runs/45254202312) SUCCESS: 2 Chromium tests in disposable CI | Real HTTP through Next.js + FastAPI + PostgreSQL, local loopback only |
| Expired guest cleanup after interlibrary transfer | New test `tests/integration/test_guest_cleanup.py` | **Latest HEAD CI result must be verified separately** |
| Public HTTPS Preview, uptime, WAF, IP throttling, guest reset, cleanup scheduler | NOT_RUN / NOT_CONFIGURED | Explicit release blockers |
| Portfolio public link, production deploy and real client onboarding | NOT_DONE | No automatic claims |

The older static `showcase/` has no authority to replace the real operational `web/` application.

## Critical merge isolation — current Vercel project

Read-only Vercel inspection confirmed that the `genova` team has the linked project
`library-network-showcase` (project `prj_0EdnHepKcZstjEYcwLYxi75gY9NI`) with the
existing `library-network-showcase-git-main-genova.vercel.app` domain. The GitHub
`main` branch of this repository is still the old V1 base
`0f583edf3a4d80cb05acc99237d2a432b8302abf`.

**DO NOT MERGE PR #4 YET** without verified release isolation. An ordinary merge to
`main` can trigger Vercel's Git integration, even if the new frontend lives in
`web/`. The Vercel API's available project response does NOT prove a safe
`rootDirectory` / build target or disabled production auto-deploy. A production
site must not be mutated under a conditional merge authorization.

Safe release alternatives to evaluate **before choosing** (all require explicit
approval for platform changes):

- Preserve `library-network-showcase` unmodified and connect a **separate**
  isolated QA/production project to the `web/` app after a backend hosting
  decision; use branch-scoped previews and only later promote a reviewed build.
- Or explicitly verify and safely reconfigure the old project/production
  branch in Vercel before merging. A read-only inspection is not permission
  to change it.

## Explicit outstanding release gates

1. **Abuse controls and spending:** PostgreSQL enforces 60 new guest workspaces
   per hour globally, 300 simultaneous active guests and 25 new loans per
   workspace. These provide hard ceilings, but one caller can exhaust all
   quotas. Add trusted-edge IP/bot rate limiting **before** a public writable
   endpoint, verify billing and budget, and run hostile burst tests. Vercel
   WAF rate limiting is available for Pro but has plan-specific pricing;
   no rate-limit rule or billable feature has been enabled.
2. **Retention:** `python -m app.application.guest_cleanup` is DRY_RUN
   by default, with bounded transactions and fail-closed cross-reference
   checks; applying requires `LIBRARY_DEMO_CLEANUP_ENABLED=1 --apply`.
   Decide a scheduler with least-privilege credential, verified environment,
   batch metrics, dry-run + readback and safe rollback; do **not** connect a
   scheduled job to a live database without specific approval.
3. **Identity and CSRF:** real HTTPS `Secure` / `__Host-` cookies, HMAC/JWKS
   rotation, Origin/Host checks and session expiry, replay and tampering need
   a separate QA environment. Next.js built-in Server Actions POST and
   Origin/Host checks are defense-in-depth, not certification on a proxy host.
4. **User experience:** guest reset (without unlimited recreation), accessible
   keyboard navigation, error recovery, mobile browser, slow connection and
   concurrent visitors need explicit QA. Never show a fake success state.
5. **Operations:** choose cost-bounded PostgreSQL hosting and Python API runtime,
   provision secrets outside GitHub/chat, migrate an **isolated** database,
   configure logging, health/ready checks, backups, alerting and domain
   routing, then test browser end-to-end under actual HTTPS. No paid
   resource or third-party integration is implicitly authorized.
6. **Merge/release contract:** reviewed code + three latest-head GitHub CI
   checks pass + no unresolved high-severity blockers + Vercel target
   proven isolated + owner's authorization for any production mutation.

## Minimal reproducible handoff

- GitHub repository: `franciscovitar/library-network-api`; PR #4 is DRAFT;
  preserve existing branch and `main`.
- App: `web/`, backend `app/`, schema `alembic/`, browser QA `qa/browser/`.
- Continue with latest commit SHA (read GitHub), never assume this document's
  snapshot remains the latest.
- Next action: validate the newly added cleanup-after-transfer test and update
  QA log; then design and test a no-cost/approved abuse and scheduler plan,
  while keeping Vercel and Production untouched.

## Verified official guidance (not automatically adopted)

- Next.js Server Action origin protection:
  https://nextjs.org/docs/app/guides/data-security
- Vercel rate-limit feature and pricing:
  https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting
  and https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing
- Vercel Cron jobs:
  https://vercel.com/docs/cron-jobs
- OWASP API authorization (BOLA):
  https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
