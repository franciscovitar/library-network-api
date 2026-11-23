"""Additional migration checks for coexistence of local and interlibrary contracts."""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_local_loan_kind_is_backward_compatible_and_restricts_branches(engine):
    with engine.connect() as connection:
        column_default = connection.execute(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name='loans' AND column_name='kind'"
            )
        ).scalar_one()
        assert "INTERLIBRARY" in column_default
        checks = connection.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname IN ('ck_loans_branches_differ', 'ck_loans_kind_valid', "
                "'ck_idempotency_records_operation_valid')"
            )
        ).all()
        assert len(checks) == 3
        definitions = dict(checks)
        assert "INTERLIBRARY" in definitions["ck_loans_branches_differ"]
        assert "LOCAL" in definitions["ck_loans_branches_differ"]
        assert "LOCAL_REQUEST" in definitions["ck_idempotency_records_operation_valid"]
