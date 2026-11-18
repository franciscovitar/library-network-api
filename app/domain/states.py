"""Closed vocabularies for the lending lifecycle (architecture V1.1).

Persisted as VARCHAR + CHECK constraints (not native PostgreSQL ENUM types) so that
adding a state later is a plain, reviewable migration. Transition *logic* is not
implemented yet; only the vocabulary and the legal adjacent pairs used by a CHECK.
"""

from enum import StrEnum


class LoanStatus(StrEnum):
    REQUESTED = "REQUESTED"
    ACTIVE = "ACTIVE"
    RETURNING = "RETURNING"
    CLOSED = "CLOSED"


# Loans in these states block any other loan of the same copy (partial unique index).
NONTERMINAL_LOAN_STATUSES = (LoanStatus.REQUESTED, LoanStatus.ACTIVE, LoanStatus.RETURNING)


class TransferStatus(StrEnum):
    PREPARED = "PREPARED"
    DISPATCHED = "DISPATCHED"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"


# Strictly sequential: no skips, no backtracking.
LEGAL_TRANSFER_STEPS = (
    (TransferStatus.PREPARED, TransferStatus.DISPATCHED),
    (TransferStatus.DISPATCHED, TransferStatus.IN_TRANSIT),
    (TransferStatus.IN_TRANSIT, TransferStatus.RECEIVED),
)


class TransferDirection(StrEnum):
    OUTBOUND = "OUTBOUND"
    RETURN = "RETURN"


class CopyStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    IN_TRANSIT = "IN_TRANSIT"
    ON_LOAN = "ON_LOAN"
    PENDING_RETURN = "PENDING_RETURN"
    RETIRED = "RETIRED"


class PhysicalCondition(StrEnum):
    GOOD = "GOOD"
    DAMAGED = "DAMAGED"


class IdempotentOperation(StrEnum):
    INTERLIBRARY_REQUEST = "INTERLIBRARY_REQUEST"
