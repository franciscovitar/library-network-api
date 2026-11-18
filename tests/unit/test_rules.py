"""Pure domain rules: no database, no HTTP."""

import pytest

from app.domain.rules import LOAN_PERIOD, canonical_request_hash, next_transfer_status
from app.domain.states import LEGAL_TRANSFER_STEPS, TransferStatus


def test_transfer_progression_is_strictly_sequential():
    path = [TransferStatus.PREPARED]
    while (nxt := next_transfer_status(path[-1])) is not None:
        path.append(nxt)
    assert [s.value for s in path] == ["PREPARED", "DISPATCHED", "IN_TRANSIT", "RECEIVED"]
    assert next_transfer_status(TransferStatus.RECEIVED) is None


@pytest.mark.parametrize("source", list(TransferStatus))
def test_next_status_agrees_with_the_legal_step_table(source):
    legal = {a: b for a, b in LEGAL_TRANSFER_STEPS}
    assert next_transfer_status(source) == legal.get(source)


def test_loan_period_is_fourteen_days():
    assert LOAN_PERIOD.days == 14


def test_canonical_hash_ignores_key_order_but_not_values():
    a = canonical_request_hash("OP", {"member_id": 1, "copy_id": 2, "destination_branch_id": 3})
    b = canonical_request_hash("OP", {"destination_branch_id": 3, "copy_id": 2, "member_id": 1})
    assert a == b and len(a) == 64
    assert a != canonical_request_hash(
        "OP", {"member_id": 2, "copy_id": 2, "destination_branch_id": 3}
    )
    assert a != canonical_request_hash(
        "OTHER", {"member_id": 1, "copy_id": 2, "destination_branch_id": 3}
    )
