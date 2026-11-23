# Library Network — isolated QA and hosting plan

**Status:** LOCAL_QA_PASS / HOSTED_QA_NOT_CREATED / PUBLIC_RELEASE_BLOCKED  
**Review date:** 2026-11-23  
**Implementation base:** `franciscovitar/library-network-api` GitHub `main` at
`327b56301c4b8a5f25b73b093b7025fad56922e4` (verified from GitHub).  
**PAS:** `franciscovitar/personal-ai-system` `main` at
`e69d67d07b517d1454505cce30d2938d65f114dc`; consulted only, unchanged.

This plan prepares a safe QA path. It does not create a Vercel project, database,
domain, secret, schedule, firewall rule, spend limit, deployment, or external
resource. `showcase/` Production remains separate from the operational `web/`
and is not a QA target.

## Current security review

| Area | Observed implementation and evidence | Finding |
|---|---|---|
| Guest capability | BFF creates UUIDv4 identities, HMAC-seals a short-lived `HttpOnly`, `SameSite=Lax` cookie; production naming uses `__Host-` and `Secure`. No bearer or signing key reaches browser code. | No local bypass found. Production cookie/proxy behavior remains unverified over HTTPS. |
| JWT and staff separation | API accepts RS256 only, pins issuer/audience/kid/JWKS, requires time claims and a short lifetime; guest and staff subject shapes are separated at the BFF and guest API. | The Base64URL test correction is present locally and covered by the current 11 JWT tests; it is not a demonstrated verifier vulnerability. Key rotation remains a hosted-QA task. |
| CSRF / Origin / Host | Mutations go through Next.js Server Actions; no browser-facing bearer API or permissive CORS middleware was found. Next.js performs Server Action origin checks by default. | Verify the real proxy `Host`/`Origin` pair and cookie behavior in the chosen QA host. Do not add wildcard `allowedOrigins`. |
| Resource authorization | Guest endpoints resolve branch, member, copy, loan, and transfer IDs through workspace membership helpers. Existing negative tests exercise foreign workspace IDs and expiry. | No cross-workspace access was demonstrated. Add hostile burst and concurrent-initialization checks before public exposure. |
| Anonymous abuse | PostgreSQL serializes creation and enforces global caps of 60 new spaces/hour, 300 active spaces, and 25 new loans per space. The code deliberately does not trust caller-supplied `X-Forwarded-For`. | **High release blocker:** global caps can be exhausted by one source. Add rate limiting at a verified trusted edge and bot controls before a public writable endpoint; quotas alone do not provide availability or cost protection. |
| Expiry cleanup | Bounded batches use `FOR UPDATE SKIP LOCKED`; cleanup checks cross-references and deletes dependencies in one transaction. CLI is dry-run by default; `--apply` also requires `LIBRARY_DEMO_CLEANUP_ENABLED=1`. Tests cover dry-run/apply, a staff grant, invalid limits, and interlibrary transfer rows. | No scheduled runner is configured. A guard failure aborts the caller's transaction; preserve fail-closed behavior and alert/inspect a blocked batch rather than retrying deletion blindly. |
| Failure behavior | SQLAlchemy work is transaction-scoped; creation quota and seed commit together, so rollback does not consume a successful workspace. API and BFF failures return errors rather than success-shaped data. | A hosted database outage, exhausted provider quota, and scheduler retry/alert behavior have not been exercised against provider infrastructure. |

These are release findings, not claims that the whole application is certified.
The main remaining security risk is public anonymous write abuse and the absence
of trusted-edge controls.

## Hosting options checked on 2026-11-23

| Option | Fit | Cost and operational constraint |
|---|---|---|
| New Vercel project for Next.js + FastAPI Python Functions, separate Neon QA database | Best fit for a later controlled QA: Vercel already supports Python/FastAPI Functions, and the stack keeps the current application shape. Keep it in a new project and use a database isolated from every other environment. | Vercel Pro currently lists a $20 monthly usage credit; usage above included amounts can be metered. WAF rate-limit rules have plan/usage-specific limits and pricing. Neon Free currently lists 100 projects, 100 CU-hours/project/month and 1 GB/project (up to 20 GB aggregate); compute/storage caps mean “free” is not a durability or availability promise. Verify the account's actual plan and spend behavior before provisioning. |
| Render free API + free PostgreSQL | Useful for a short disposable experiment only. | Free web services spin down after 15 minutes idle; free PostgreSQL expires 30 days after creation. This does not meet a stable recruiter-facing availability or persistence target. Paid web and PostgreSQL plans have separate monthly charges. |
| Existing `library-network-showcase` project | Not suitable. | It is the old static showcase with existing Production domains and deployment history. Preserve it; do not connect `web/`, FastAPI, or QA secrets to it. |

Vercel announced general availability of its Python runtime on 2026-10-15;
FastAPI runs as a Function. For a later QA prototype, separately measure cold
start, connection reuse, timeout behavior, and package/build compatibility.
The production API is not proven compatible merely because local tests pass.

## Proposed isolated QA topology

```text
Recruiter / invited reviewer
        |
Vercel WAF + protected QA access
        |
New Vercel QA project (Next.js BFF + FastAPI Python Function)
        |                         |
        | signed short-lived JWT   +-- scheduled cleanup command (disabled)
        |
Dedicated Neon QA project / PostgreSQL branch
        - synthetic-only data
        - QA-only roles and keys
        - never shared with showcase or future production
```

For the first hosted QA checkpoint, use a separate Vercel project and a separate
Neon QA project (or a provider-approved disposable branch). Do not bind any QA
deployment to `library-network-showcase`, its Production domain, or an existing
database. Keep the QA URL private/protected while evaluating it; no public
portfolio link until the abuse gates pass.

### Controls required before creating hosted QA

1. Owner reviews the target Vercel team plan, current usage, WAF rate-limit
   pricing, automatic pause/spend controls, Neon limits, region, and deletion
   behavior. The available free limits are not assumed sufficient.
2. Create a dedicated QA project only after that review. Use unique
   `QA_DATABASE_URL`, `LIBRARY_API_SIGNING_KEY_PKCS8`, `LIBRARY_JWKS_JSON`,
   `LIBRARY_GUEST_COOKIE_SECRET`, `LIBRARY_JWT_ISSUER`, and audience values.
   Store them in provider environment settings; never copy production values.
3. Apply migrations once using a separate migration identity. Runtime identity
   gets only the DML rights it needs. Cleanup runs with a separate credential
   limited to the isolated QA database. Do not run migrations on app startup.
4. Enable edge limits for guest-workspace creation and writes on the API host,
   keyed only by provider-verified source identity; add bot challenge/block
   rules where justified. Keep PostgreSQL global limits as a second ceiling.
   Never persist raw IP addresses in application tables.
5. Require HTTPS; verify `Secure`/`__Host-` cookies, Server Action Origin/Host,
   issuer/audience/kid rotation, and direct API host protections. Do not trust
   forwarded headers unless the selected provider strips and rewrites them.
6. Make guest cleanup dry-run the first operation. Before any apply, capture
   candidate counts, enforce the 25-row batch maximum, verify the isolated DB,
   run a readback, and alert on exceptions or blocked foreign references. Do
   not schedule it until its credentials, retry policy, and alert path are
   reviewed. Use bounded retries with backoff; never retry an ambiguous commit
   by widening the deletion scope.
7. Monitor API 4xx/5xx and latency, database connection/compute/storage usage,
   quota rejects, WAF rejects, and cleanup counts/failures. Set an owner-approved
   hard spend ceiling before enabling any billable edge rule. A spend stop may
   pause QA; it must not silently disable a safety limit on a public app.
8. Use synthetic seed data only. For QA, treat the database as disposable and
   rebuild from migrations + seed. If later product requirements require
   durable visitor data, select a paid backup/restore policy and test restore
   before exposing the service.

### Release and rollback sequence

1. Provision nothing until the owner approves the specific provider resources
   and expected spend. Preview builds are not an iterative debugging runner.
2. Build one protected QA checkpoint on isolated resources, then verify the
   real HTTPS browser journey, WAF limits, quotas, concurrent visitors,
   migration, cleanup dry-run, health/readiness, and failure recovery.
3. Record exact deployment SHA, database identity (not credentials), migration
   head, WAF rules, spend ceiling, monitoring, and restore point.
4. Roll back by routing the QA project to the previous known-good deployment;
   do not restore or point at `showcase` Production. For a bad migration, use a
   tested forward repair or restore only the QA database snapshot.
5. Public release remains a separate decision after all security and cost gates.

## Current local QA evidence

The run below used a loopback-only FastAPI + Next.js development stack and a
disposable PostgreSQL 17 container with a tmpfs data directory. It did not build
the FastAPI Docker image and did not contact a hosted database.

- Python: `184 passed`; JUnit guard: `total=184`, `failed=0`, `skipped=0`,
  `integration_passed=161`, `unit_passed=23`.
- Ruff lint and format: PASS.
- Web Node tests: `7 passed`; TypeScript: PASS; Next.js production build: PASS.
- Playwright Chromium: `4 passed`, including checkout/return, workspace reset,
  interlibrary roundtrip, and a 390px keyboard/mobile layout check.
- Chromium source: system `/usr/bin/chromium`; Playwright's browser download was
  blocked by the environment CDN returning HTTP 403. No TLS setting was
  weakened.
- Pytest emitted two dependency deprecation warnings (AnyIO's old pytest alias
  and Starlette's `httpx` TestClient integration); no test failed.
- GitHub readback for the base SHA returned no status checks and no check runs;
  the local results above do not claim hosted CI PASS.
- No GitHub Actions or Vercel Preview build was used for iterative debugging.

## Official references checked

- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Vercel Pro plan](https://vercel.com/docs/plans/pro-plan)
- [Vercel WAF rate limits](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)
- [Vercel WAF usage and pricing](https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing)
- [Vercel `git.deploymentEnabled`](https://vercel.com/docs/project-configuration/git-configuration)
- [Neon Free plan update, 2026-10-02](https://neon.com/blog/neon-free-plan-1-gb-per-project)
- [Render free limits](https://render.com/docs/free)
