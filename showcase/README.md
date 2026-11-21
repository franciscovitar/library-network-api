# Library Network API — public interactive showcase

Static website served separately from the **real, locally runnable** Python/FastAPI + PostgreSQL backend.

- `model.js` encodes a deterministic *illustration* of domain transitions. It does not emulate SQL transactions, concurrency, row locking or HTTP.
- The original backend, migrations, PostgreSQL tests and reproducible HTTP scenario remain in this repository's root.
- No API credentials, live accounts, visitor data, remote requests or external dependencies.
- `node --test model.test.mjs` verifies the synthetic state machine.

## Deployment

Vercel project: use `showcase` as **Root Directory**, framework **Other**, output directory `.`. Do not deploy the root FastAPI service publicly: it is intentionally unauthenticated.

The hosted UI is an explanatory **front-end demonstration**, not evidence that SQL or concurrent backend tests are running in a browser.
