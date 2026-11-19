# ADR 0002: Lifecycle commands, row locking and idempotency

- **Status:** accepted (2026-11-18). Source contract: architecture V1.1 (PAS PR #667). Builds on ADR 0001.

## Decisions

1. **One transaction per command, owned by the caller.** Use cases (`app/application/*`) take a
   `Session`, never commit, and run inside `sessionmaker.begin()` opened by the route. Any exception
   rolls back every row the command touched. Sessions are request-scoped, never shared.
2. **Fixed lock order: idempotency claim -> copy -> loan -> transfer.** Commands on an existing loan or
   transfer first do an *unlocked* lookup of the copy id, then lock copy, loan and transfer, and only
   then re-read and validate state. Because every command locks the copy first, two commands cannot
   hold locks in opposite orders. READ COMMITTED (the PostgreSQL default) is enough.
3. **Idempotent request via claim-first.** The command pre-allocates the loan id (`nextval`), claims
   `(operation, key)` with `INSERT ... ON CONFLICT DO NOTHING`, locks the copy, validates, inserts. The
   claim's FK to `loans` is `DEFERRABLE INITIALLY DEFERRED`, so claim and loan commit together or not at
   all. A concurrent same-key request blocks on the conflicting insert until the first transaction ends:
   after commit it replays, after rollback it takes over. Result: deterministic convergence on one loan.
4. **A rejected request does not consume its key.** Validation failures roll back the claim with the rest.
   Retrying the same key with a corrected body is allowed; retrying the same rejected request converges
   on the same rejection. *Trade-off:* clients cannot rely on a replay of an error.
5. **Replay returns the resource, not a snapshot.** Replays return `200` with the loan's current state and
   the same identity (V1.1: "returns prior resource"). Storing response bodies was avoided as extra
   state with no V1 benefit.
6. **Request hash = SHA-256 over canonical JSON of operation + body** (sorted keys, no whitespace). The
   key is not part of the hash. Same key + different hash -> `409 idempotency_key_reuse`.
7. **Receipt is where location changes.** `current_branch_id` is updated only when a transfer is
   `RECEIVED`; `IN_TRANSIT` never moves the copy. Return reception sets `AVAILABLE` (GOOD) or `RETIRED`
   plus `physical_condition = DAMAGED`, and closes the loan, in the same transaction as the history event.
8. **Stable errors.** Domain errors carry a machine-readable `code` (404/409); validation is `422
   validation_error`; a database constraint that slips past the checks is `409 constraint_conflict`;
   anything else is a logged, sanitized `500 internal_error`.
9. **Fixed loan period (14 days)**, no renewals, fines or cancellation: out of V1 scope.
10. **Test strategy for concurrency.** Real PostgreSQL, separate connections released by a barrier, an
    injected delay between claim and copy lock, and an injected delay *after* a lock is taken (so a
    missing lock produces a visible race), `lock_timeout` so deadlocks fail loudly, and manual
    mutation checks proving the tests fail when locks or checks are removed.

## Consequences / limits

- The mixed-command stress test proves no deadlock/500, not lock necessity (constraints also stop
  those races); the targeted post-lock-delay tests are the ones that prove the locks.
- Unauthenticated writes: local demo only.
- No CI yet: all evidence is from local runs.
