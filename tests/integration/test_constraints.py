"""Database-level invariants (second line of defence) against real PostgreSQL.

Each test runs inside a transaction that is rolled back (see the ``db`` fixture). Expected
violations are provoked inside SAVEPOINTs and identified by the exact PostgreSQL constraint
name, so a test cannot pass because of an unrelated error.

Seed reference: branches 1-3, members 1-6 (6 disabled), copies 1-10 (10 retired).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.persistence.models import (
    Branch,
    Copy,
    IdempotencyRecord,
    Loan,
    Transfer,
    TransferEvent,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def loan(status="REQUESTED", *, copy_id=1, member_id=1, origin=1, dest=2, **overrides) -> Loan:
    """Build a loan consistent with its status unless overridden."""
    fields = dict(
        member_id=member_id,
        copy_id=copy_id,
        origin_branch_id=origin,
        destination_branch_id=dest,
        status=status,
        requested_at=T0,
    )
    if status != "REQUESTED":
        fields |= dict(started_at=T0 + timedelta(days=1), due_at=T0 + timedelta(days=15))
    if status in ("RETURNING", "CLOSED"):
        fields |= dict(borrower_returned_at=T0 + timedelta(days=5), return_condition="GOOD")
    if status == "CLOSED":
        fields |= dict(closed_at=T0 + timedelta(days=8))
    return Loan(**(fields | overrides))


def violation(session: Session, *objects) -> str:
    """Insert objects, expect an IntegrityError, return the violated constraint/index name."""
    with pytest.raises(IntegrityError) as info:
        with session.begin_nested():
            session.add_all(objects)
            session.flush()
    return info.value.orig.diag.constraint_name


def persisted(session: Session, *objects) -> None:
    with session.begin_nested():
        session.add_all(objects)
        session.flush()


# --- loans: one nonterminal loan per copy --------------------------------------------------


@pytest.mark.parametrize("existing", ["REQUESTED", "ACTIVE", "RETURNING"])
def test_second_loan_for_same_copy_is_rejected_while_first_is_nonterminal(db, existing):
    persisted(db, loan(existing, copy_id=1))
    assert (
        violation(db, loan("REQUESTED", copy_id=1, member_id=2)) == "uq_loans_copy_id_nonterminal"
    )


def test_closed_loans_do_not_block_a_new_loan_but_an_open_one_does(db):
    persisted(db, loan("CLOSED", copy_id=2), loan("CLOSED", copy_id=2, member_id=3))
    persisted(db, loan("REQUESTED", copy_id=2, member_id=4))  # history does not block
    assert (
        violation(db, loan("REQUESTED", copy_id=2, member_id=5)) == "uq_loans_copy_id_nonterminal"
    )


def test_different_copies_can_have_open_loans_simultaneously(db):
    persisted(db, loan("REQUESTED", copy_id=3), loan("ACTIVE", copy_id=4, member_id=2))


# --- loans: state/date coherence and references --------------------------------------------


@pytest.mark.parametrize(
    ("status", "overrides", "expected"),
    [
        ("ACTIVE", dict(started_at=None, due_at=None), "ck_loans_started_after_requested"),
        ("PAUSED", dict(), "ck_loans_status_valid"),
        ("REQUESTED", dict(closed_at=T0), "ck_loans_closed_at_matches_status"),
        ("CLOSED", dict(closed_at=None), "ck_loans_closed_at_matches_status"),
        ("RETURNING", dict(borrower_returned_at=None), "ck_loans_return_fields_match_status"),
        ("RETURNING", dict(return_condition=None), "ck_loans_return_fields_match_status"),
        ("ACTIVE", dict(due_at=T0), "ck_loans_due_after_start"),
        ("CLOSED", dict(return_condition="LOST"), "ck_loans_return_condition_valid"),
        ("REQUESTED", dict(dest=1), "ck_loans_branches_differ"),
        ("REQUESTED", dict(member_id=999), "fk_loans_member_id_members"),
        ("REQUESTED", dict(copy_id=999), "fk_loans_copy_id_copies"),
        ("REQUESTED", dict(dest=999), "fk_loans_destination_branch_id_branches"),
    ],
)
def test_invalid_loan_rows_are_rejected(db, status, overrides, expected):
    overrides = {"copy_id": 5} | overrides
    assert violation(db, loan(status, **overrides)) == expected


# --- copies / catalogue ---------------------------------------------------------------------


def test_copy_code_is_unique(db):
    duplicate = Copy(code="CP-0001", book_id=1, owning_branch_id=1, current_branch_id=1)
    assert violation(db, duplicate) == "uq_copies_code"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (dict(status="LOST"), "ck_copies_status_valid"),
        (dict(physical_condition="BROKEN"), "ck_copies_condition_valid"),
        (dict(owning_branch_id=999), "fk_copies_owning_branch_id_branches"),
        (dict(current_branch_id=999), "fk_copies_current_branch_id_branches"),
        (dict(book_id=999), "fk_copies_book_id_books"),
    ],
)
def test_invalid_copy_rows_are_rejected(db, overrides, expected):
    row = dict(code="CP-NEW", book_id=1, owning_branch_id=1, current_branch_id=1) | overrides
    assert violation(db, Copy(**row)) == expected


def test_branch_name_is_unique(db):
    assert violation(db, Branch(name="Central Branch")) == "uq_branches_name"


# --- transfers and history ------------------------------------------------------------------


def transfer(loan_id, direction="OUTBOUND", status="PREPARED", **overrides) -> Transfer:
    fields = dict(
        loan_id=loan_id,
        direction=direction,
        origin_branch_id=1,
        destination_branch_id=2,
        status=status,
        created_at=T0,
    )
    return Transfer(**(fields | overrides))


def test_at_most_one_transfer_per_loan_and_direction(db):
    first = loan("REQUESTED", copy_id=6)
    persisted(db, first)
    persisted(
        db,
        transfer(first.id, "OUTBOUND"),
        transfer(first.id, "RETURN", origin_branch_id=2, destination_branch_id=1),
    )
    assert violation(db, transfer(first.id, "OUTBOUND")) == "uq_transfers_loan_id_direction"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (dict(status="RECEIVED"), "ck_transfers_received_at_matches_status"),
        (dict(received_at=T0), "ck_transfers_received_at_matches_status"),
        (dict(destination_branch_id=1), "ck_transfers_branches_differ"),
        (dict(direction="SIDEWAYS"), "ck_transfers_direction_valid"),
        (dict(status="LOST"), "ck_transfers_status_valid"),
    ],
)
def test_invalid_transfer_rows_are_rejected(db, overrides, expected):
    parent = loan("REQUESTED", copy_id=7)
    persisted(db, parent)
    assert violation(db, transfer(parent.id, **overrides)) == expected


def event(transfer_id, from_status, to_status) -> TransferEvent:
    return TransferEvent(
        transfer_id=transfer_id, from_status=from_status, to_status=to_status, occurred_at=T0
    )


@pytest.fixture
def a_transfer(db) -> Transfer:
    parent = loan("REQUESTED", copy_id=8)
    persisted(db, parent)
    t = transfer(parent.id)
    persisted(db, t)
    return t


def test_history_accepts_the_sequential_path_once(db, a_transfer):
    persisted(
        db,
        event(a_transfer.id, None, "PREPARED"),
        event(a_transfer.id, "PREPARED", "DISPATCHED"),
        event(a_transfer.id, "DISPATCHED", "IN_TRANSIT"),
        event(a_transfer.id, "IN_TRANSIT", "RECEIVED"),
    )


def test_history_state_cannot_be_recorded_twice(db, a_transfer):
    persisted(db, event(a_transfer.id, None, "PREPARED"))
    assert (
        violation(db, event(a_transfer.id, None, "PREPARED"))
        == "uq_transfer_events_transfer_id_to_status"
    )


@pytest.mark.parametrize(
    ("from_status", "to_status", "expected"),
    [
        ("PREPARED", "RECEIVED", "ck_transfer_events_step_is_legal"),  # skip
        ("RECEIVED", "IN_TRANSIT", "ck_transfer_events_step_is_legal"),  # backtrack
        ("DISPATCHED", "DISPATCHED", "ck_transfer_events_step_is_legal"),  # no-op
        (None, "DISPATCHED", "ck_transfer_events_initial_event_is_prepared"),
        ("PREPARED", "PREPARED", "ck_transfer_events_initial_event_is_prepared"),
    ],
)
def test_illegal_history_steps_are_rejected(db, a_transfer, from_status, to_status, expected):
    assert violation(db, event(a_transfer.id, from_status, to_status)) == expected


# --- idempotency records --------------------------------------------------------------------


def next_loan_id(db) -> int:
    return db.execute(text("SELECT nextval(pg_get_serial_sequence('loans', 'id'))")).scalar_one()


def claim(key, resource_id, **overrides) -> IdempotencyRecord:
    fields = dict(
        operation="INTERLIBRARY_REQUEST",
        key=key,
        request_hash=HASH,
        resource_type="LOAN",
        resource_id=resource_id,
        created_at=T0,
    )
    return IdempotencyRecord(**(fields | overrides))


def test_idempotency_key_is_unique_per_operation(db):
    first = loan("REQUESTED", copy_id=9)
    persisted(db, first)
    persisted(db, claim("demo-req-001", first.id))
    assert violation(db, claim("demo-req-001", first.id)) == "uq_idempotency_records_operation_key"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (dict(request_hash="short"), "ck_idempotency_records_request_hash_is_sha256_hex"),
        (dict(key=""), "ck_idempotency_records_key_length"),
        (dict(operation="OTHER"), "ck_idempotency_records_operation_valid"),
        (dict(resource_type="TRANSFER"), "ck_idempotency_records_resource_type_valid"),
    ],
)
def test_invalid_idempotency_rows_are_rejected(db, overrides, expected):
    first = loan("REQUESTED", copy_id=9)
    persisted(db, first)
    key = overrides.pop("key", "k")
    assert violation(db, claim(key, first.id, **overrides)) == expected


def test_key_can_be_claimed_before_its_loan_within_one_transaction(db):
    """Claim-first design: pre-allocated loan id, claim, then insert the loan."""
    loan_id = next_loan_id(db)
    persisted(db, claim("claim-first", loan_id))
    persisted(db, loan("REQUESTED", copy_id=9, id=loan_id))
    db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))  # force the deferred FK check now: passes


def test_claim_without_its_resource_fails_when_constraints_are_checked(db):
    with pytest.raises(IntegrityError) as info:
        with db.begin_nested():
            db.add(claim("orphan", resource_id=987654321))
            db.flush()  # allowed: the FK is deferred...
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))  # ...but never at commit time
    assert info.value.orig.diag.constraint_name == "fk_idempotency_records_resource_id_loans"


def test_committing_a_claim_without_a_resource_is_impossible(seeded_engine):
    """Real commit (not a savepoint): the orphan claim must not be persisted."""
    with pytest.raises(IntegrityError) as info:
        with Session(seeded_engine) as session:
            session.add(claim("orphan-commit", resource_id=987654321))
            session.commit()
    assert info.value.orig.diag.constraint_name == "fk_idempotency_records_resource_id_loans"
    with Session(seeded_engine) as session:
        assert session.execute(text("SELECT count(*) FROM idempotency_records")).scalar_one() == 0
