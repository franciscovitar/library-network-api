"""Use cases: one explicit database transaction per command, locks taken in a fixed order.

Lock order (V1.1): idempotency claim (request only) -> copy -> loan -> transfer.
Each function runs inside a transaction owned by the caller (`sessionmaker.begin()`); it
never commits, so any exception rolls back every row it touched.
"""

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)
