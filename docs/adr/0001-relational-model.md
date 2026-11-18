# ADR 0001: Initial relational model and migrations

- **Status:** accepted (2026-11-18). Source contract: architecture V1.1 (PAS PR #667).
- **Scope:** schema, migration, seed, DB-level tests. The lending lifecycle is *not* implemented.

## Decisions

1. **States as `VARCHAR` + `CHECK`, not PostgreSQL `ENUM`.** Adding a state is an ordinary migration
   (no `ALTER TYPE` restrictions); vocabularies live in `app/domain/states.py` and the CHECKs are
   generated from them in the models. The migration repeats the literals on purpose, so it stays a
   frozen, reviewable artifact; a no-drift test compares it to the models.
2. **Hand-written reviewed migration, naming convention.** Deterministic constraint names
   (`uq_`, `ck_`, `fk_`, `ix_`, `pk_`) make failures identifiable: tests assert the exact violated
   constraint name rather than "some error".
3. **One nonterminal loan per copy** via a partial unique index on `status IN
   ('REQUESTED','ACTIVE','RETURNING')`. A borrower hand-back leaves the loan `RETURNING`, so the
   copy cannot be re-requested until the return transfer is received (V1.1 refinement of the TP).
4. **Date/state coherence in CHECKs** (e.g. `CLOSED` iff `closed_at`, `RETURNING/CLOSED` require the
   borrower-return fields, `due_at > started_at`, `RECEIVED` iff `received_at`).
5. **History integrity in the database:** `UNIQUE (transfer_id, to_status)` and a CHECK that only the
   adjacent steps `PREPARED->DISPATCHED->IN_TRANSIT->RECEIVED` (or the initial `NULL->PREPARED`) can be
   recorded, so a duplicate receipt or a skipped/backward step cannot persist even if application
   code is wrong.
6. **Idempotency claim and resource commit together.** `idempotency_records.resource_id` is `NOT NULL`
   with a `DEFERRABLE INITIALLY DEFERRED` FK to `loans`. The future request command can pre-allocate
   the loan id (`nextval`), claim `(operation, key)` first, take the copy lock, insert the loan, and
   commit; a claim without its loan cannot be committed. Tested with a real commit.
   *Trade-off:* the key is tied to loans (the only idempotent operation in V1); a second resource
   type would need a migration.
7. **No `now()` defaults; timezone-aware columns.** Timestamps come from an injectable clock so seed
   and tests stay deterministic.
8. **Seed is insert-only and refuses non-empty databases.** Explicit ids give stable documentation;
   sequences are advanced past the maximum. Data is fully synthetic (ISBN-like values with the
   unassigned `000` prefix, no personal data).
9. **Test isolation:** integration tests create and drop their own throwaway databases on a
   disposable server (`compose.test.yaml`) and build the schema with Alembic. The compose demo
   database is never touched and publishes no host port.

## Consequences / not yet done

- Application-level transactions, `FOR UPDATE` lock ordering and idempotent replay are untested because
  they do not exist yet; the DB-level race test only proves the unique index's single-winner behavior.
- `copies.current_branch_id` vs. transfer state consistency is a future application invariant, not
  a constraint.
