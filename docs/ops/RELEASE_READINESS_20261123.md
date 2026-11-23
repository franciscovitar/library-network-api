# Library Network — Release and merge gates (2026-11-23)

**Scope:** PR #4 merged into `main` as `3c514476e1ce6f6036fab2df25174317f4eb1334` (code only; no public release). Follow-up development stays in an isolated branch.  
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
| Public HTTPS Preview, uptime, WAF, IP throttling, cleanup scheduler | NOT_RUN / NOT_CONFIGURED | Explicit release blockers |
| Portfolio public link, production deploy and real client onboarding | NOT_DONE | No automatic claims |

The older static `showcase/` has no authority to replace the real operational `web/` application.

## Verified merge isolation — existing Vercel showcase

Read-only inspection confirmed `genova/library-network-showcase` project
`prj_0EdnHepKcZstjEYcwLYxi75gY9NI`, whose Production deployment originates
from GitHub `main` at `0f583edf3a4d80cb05acc99237d2a432b8302abf`.
The existing public showcase must remain intact independently from the real `web/`.

**Prepared in feature branch only:** `showcase/vercel.json` retains its
existing security headers and now includes Vercel's official
[`git.deploymentEnabled`](https://vercel.com/docs/project-configuration/git-configuration)
with `main:false`. The PR branch is also temporarily excluded for a direct
probe; no Vercel settings/Production/domains/aliases/secrets were modified.

**Direct verification of this Vercel configuration path:** commit
`54e0c20f5ca4eb5fea37233cc4d2355a786ee9f1` previously produced a READY
preview `dpl_Cr5ttozwQ6C9ra8ZijET5jrF4ED4`. After adding the PR-branch
veto, commit `b4ff4e83e65f1dbcf26d70737b71ca67da0d33dd` produced
**no Vercel deployment** on subsequent readback, and the project's latest
deployment remained the previous one. This supports that the project reads the
configuration from `showcase/vercel.json`, but does not guarantee that unrelated
CLI/API/manual deploy sources cannot run.

**Automated guard:** PR #6 replaces the earlier branch-specific check with a
guard on every PR targeting `main`. It passes when `showcase/` is unchanged;
otherwise it allows only additions of literal branch vetoes (`false`) or
turning an enabled branch into a veto in `showcase/vercel.json`. Existing
vetoes and `main:false` must remain; content/headers, other config, executable
mode, symlink mode, and wildcard branch rules are rejected. Twelve focused
unit tests exercise the policy. The check runs after the PR event and is not
a pre-deployment control: read back Vercel's branch veto before each push and
confirm no deployment before merge.

**Code merge gate:** allow merge only with Python/PostgreSQL, Next.js, browser
and showcase-merge-safety checks all PASS on the exact head, unchanged Vercel
Git veto, and current GitHub mergeability. Then read Vercel Production back
and verify the known deployment remains assigned. This is **not** an approval
to deploy the real application, rotate keys, write to live databases, or
modify billing. The public new-app release still requires separate hosting,
IP/bot protection, cleanup scheduling, isolated DB, secrets and HTTPS QA.

**Rollback:** if Vercel unexpectedly publishes from Git after main moves,
stop all further changes, inspect Production/deployment metadata and restore
the previously known READY deployment through an explicitly authorized Vercel
rollback. To resume future old-showcase automatic Git releases, review and
revert the deployment veto in a dedicated change.

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

## Follow-up — create a fresh anonymous workspace (development only)

- The server action `restartDemo` calls the existing transaction-backed guest
  creation endpoint with a new UUIDv4 subject, **then** replaces the signed,
  HttpOnly visitor cookie only after a successful response. If the PostgreSQL
  global creation/active-workspace budget rejects the request (429), the
  existing browser session remains intact; there is no client-only reset.
- The guest dashboard provides `Crear otra biblioteca temporal`. Its text
  explicitly distinguishes **switching to a fresh workspace** from deleting
  or revoking the former one. Expired records remain subject to the existing
  safe cleanup process, which has NOT been scheduled.
- A Chromium test checks that a borrower can open a new, isolated guest
  library while the prior guest workspace and loan persist independently.
- Verification state on the verified current `main` base: local Python/PostgreSQL
  184 passed (161 integration + 23 unit), Web tests/typecheck/build PASS, and
  local Chromium browser QA 4 passed. The follow-up was locally tested with a
  disposable PostgreSQL 17 container. GitHub readback for this exact base has
  no status checks or check runs. No public hosting, live database, real secrets,
  WAF rule, cron, budget or Production change.

## Continuation — isolated QA preparation (2026-11-23)

- GitHub `main` rechecked at `327b56301c4b8a5f25b73b093b7025fad56922e4`;
  local `work` starts from that commit. The Base64URL test correction is still
  an uncommitted local change and is included in the isolated follow-up.
- Vercel Production readback still identifies the old static showcase and its
  known Production commit `0f583edf3a4d80cb05acc99237d2a432b8302abf`.
- See [the isolated QA plan](QA_ISOLATION_PLAN_20261123.md) for the security
  review, provider comparison, local evidence, and unprovisioned QA topology.
- A new exact branch-name Vercel Git veto is included before publishing the
  isolated branch; no Vercel settings or deployment were changed.
