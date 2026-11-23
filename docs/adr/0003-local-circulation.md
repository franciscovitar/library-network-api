# ADR 0003 — Local circulation alongside the interlibrary contract

**State:** PROPOSED (development branch; not deployed). Date: 2026-11-23.

## Motivation

The prior schema requires origin and destination branches to differ; this correctly
models interlibrary loans but prevents ordinary checkout/return at a single branch.
A browser-only imitation is not acceptable. Existing PostgreSQL locks, idempotency
and interlibrary state invariants must be preserved.

## Decision

- Add `loans.kind` with default `INTERLIBRARY` for historic rows and explicit `LOCAL`.
- Keep the named `ck_loans_branches_differ` constraint with a kind-dependent condition.
- A local loan starts `ACTIVE` immediately, due in 14 days, with no transfer records.
- A local return closes it and releases or retires the same physical copy.
- Reuse physical-copy row locks, one transaction per command, and the existing
  unique partial index disallowing two nonterminal loans for the same copy.
- Local issues use a separate idempotency operation namespace and durable claim.
- The legacy interlibrary transfer/return workflow remains unchanged.
- A downgrade fails safely when local data or claims remain, rather than deleting it.

## Security and release boundary

This API is still unauthenticated and loopback-only. No public deployment or
customer data until auth, role/branch scope, session/CSRF, rate limit, demo
isolation, and production QA are implemented and verified.

## Evidence

The code is not automatically tested by this ADR. Real PostgreSQL migrations,
concurrency, wrong-branch, bad-return, replay, and the full existing suite must
pass in commit-linked GitHub Actions before the PR may be merged.
