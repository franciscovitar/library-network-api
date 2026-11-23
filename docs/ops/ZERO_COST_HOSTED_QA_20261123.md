# Library Network — zero-additional-cost hosted QA candidate

**Date:** 2026-11-23. **Status:** RESEARCHED_CANDIDATE / NOT_PROVISIONED / NOT_DEPLOYED.
**Repository base:** `franciscovitar/library-network-api` main `9018d686546394ab096ff0b1ed59a91a46c9573b`.
**Decision constraint:** maximum additional infrastructure spend **USD 0**; do not use Neon, existing client environments, paid tiers or stored payment methods. Source evaluations below are not claims of a tested account or deployment.

## Smallest plausible hosted QA

- **Database candidate:** a new, dedicated **Aiven PostgreSQL Free** service, in an account/project without a payment method. Official Aiven documentation says the service needs no credit card, has no time limit and cannot incur automatic fees on Free. Available resources: one node, 1 CPU, 1 GB RAM, 1 GB storage, automatic backups and **20 max connections**. Aiven may power off inactive free services. This is not an SLA-backed recruiter production database.
- **App runtime candidate:** two separate **Render Free web services**, one for the existing Next.js `web/` BFF (requires server runtime for Server Actions) and one for existing Python FastAPI. Render documents both runtime types. If Render requires a payment method at signup or deployment, **STOP**, do not add a card and do not proceed. Confirm both service plans explicitly show Free before creating any service.
- **Important constraint:** Render's Free web services **share 750 active-instance hours per workspace each calendar month**, have 15-minute idle spin-down and may take about a minute to resume; usage beyond included bandwidth or build minutes **may be billed if a payment method is present**. Without a payment method Render says services/builds are instead suspended. Two always-active services cannot both stay running throughout an entire month within the shared hours. This makes the combination appropriate only for bounded, disposable QA, **not** a friction-free recruiter portfolio launch.
- Do **not** use Render's Free Postgres for persistent data: it expires after 30 days, with no automatic backups. Do not use the existing Vercel Pro team for an assumed hard-USD-0 deploy: its metered budgets are checked periodically rather than instantaneously, and team-level pause could impact unrelated sites.

### Local compatibility work in this PR

The FastAPI engine pool is intentionally **2 base + 1 overflow connections per process**, timeout 5 seconds. This conserves Aiven Free's 20-connection limit relative to SQLAlchemy's larger default pool. A local unit test verifies the configuration.

**It is not a global limit.** Multiple instances, migration jobs and administrative connections share the provider cap. Before provisioning, choose and verify a bounded number of API instances, leave connection headroom, observe pool timeouts, and test the real provider with an isolated QA database. The local unit test uses temporary SQLite to verify the pool *configuration only*; prior PostgreSQL integration tests remain necessary for transactional behavior.

### Hard gates before any resource is created

1. Owner approves the **specific free Aiven and Render resources** and observes that signup does not require credit card/payment methods. Confirm there is no pre-existing billing arrangement on the chosen accounts. If any charge/paid upgrade is offered or required, stop.
2. The operator verifies the selected Aiven plan is **Free $0**, storage and connection quotas, PostgreSQL major version, region, service suspend policy and TLS CA distribution. Use `sslmode=verify-full` with the official project CA when feasible; do not put database URLs, CA secrets, JWT private keys or cookie secrets in GitHub.
3. Verify that both Render deployments use **Free** and that no chargeable extra service, disk, cron, paid worker or add-on is selected. Do not assume the sign-up flow remains card-free.
4. Add a **private QA access gate** and server-side quotas/edge protections before exposing anonymous write operations. A random URL is not an access control. Do not assume global guest-workspace quotas prevent abuse.
5. Ensure independent QA-only database roles, JWT keys, cookie signing secret and migrations; **no existing Production or client environment** may be reused.
6. Before the first deploy, adjust/measure the `web/lib/api.ts` **12-second server-to-server timeout** against Render cold starts (~one minute). The current behavior would likely fail the first visitor's operation after an idle period. Do not silently relax timeouts for public traffic; do controlled warm/cold QA.
7. Run migrations with a dedicated, explicitly approved migration identity only after QA resource isolation is verified. Never migrate during app startup. Cleanup remains dry-run and unscheduled until separately approved.
8. Test over HTTPS: guest cookie and Origin/Host, token exchange, DB transaction/loan/return, access isolation, connection exhaustion, cold start, failure recovery, cleanup dry-run, abuse throttling and reset; record deployment and migration SHA.
9. Public recruiter deployment is a **separate release gate**. If cold-start, account/payment or abuse-control requirements make this option unsuitable, keep the app local until a genuinely zero-charge alternative is verified.

## What's authorized and observed

This PR **only** changes local connection-pool configuration, adds a unit test, writes this evidence/plan and expands the exact Vercel branch veto in the existing static showcase config. It does **not** create Aiven/Render accounts, projects, services, databases, user accounts, credentials, WAF rules, jobs, migration runs or deployments. It does not alter Production. A local bounded-pool unit test passed on Python 3.13 / SQLAlchemy 2.0; the whole app's tests and hosted QA remain to be reverified on the exact PR commit.

## Official references (verified 2026-11-23)

- Aiven PostgreSQL Free limits and suspension: https://aiven.io/docs/products/postgresql/concepts/pg-free-tier
- Aiven Free billing promise: https://aiven.io/free-tier
- Aiven TLS and certificate validation: https://aiven.io/docs/products/postgresql/howto/connect-python
- Render Free web-service quotas, billing and cold starts: https://render.com/docs/free
- Render Next.js server web-service support: https://render.com/docs/deploy-nextjs-app
- Vercel budget delay and project/team effects: https://vercel.com/docs/spend-management
