"""Domain errors with stable, machine-readable codes (mapped to HTTP in app/api/errors.py)."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    """The request is valid but conflicts with the current state (or an idempotency key)."""

    status_code = 409
