"""Pure domain rules (no I/O): transfer ordering, loan period, idempotency hashing."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from app.domain.states import LEGAL_TRANSFER_STEPS, TransferStatus

# Fixed loan period for V1 (no renewals, no fines).
LOAN_PERIOD = timedelta(days=14)


def next_transfer_status(current: TransferStatus) -> TransferStatus | None:
    """The only legal successor of `current`, or None when the transfer is final."""
    for source, target in LEGAL_TRANSFER_STEPS:
        if source == current:
            return target
    return None


def canonical_request_hash(operation: str, payload: dict[str, Any]) -> str:
    """SHA-256 over the operation plus a canonical JSON rendering of the payload.

    Key order and whitespace never change the hash; any change of value does. The idempotency
    key itself is deliberately not part of it (it identifies the request, the hash its content).
    """
    canonical = json.dumps(
        {"operation": operation, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
