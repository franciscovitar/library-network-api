"""Stable error payloads: {"error": {"code": "...", "message": "..."}}.

Domain errors map to 404/409; request validation to 422; a database constraint that slips past
the application checks becomes a stable 409; anything else is a sanitized 500 (details are
logged server-side only, never returned).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.domain.errors import DomainError

logger = logging.getLogger("app.api")


def _payload(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _payload(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return _payload(422, "validation_error", problems or "Invalid request.")

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # Expected race outcome when a database constraint is the one that stops a conflict.
        logger.warning(
            "constraint conflict: %s",
            getattr(exc.orig, "diag", None) and exc.orig.diag.constraint_name,
        )
        return _payload(409, "constraint_conflict", "The request conflicts with the current state.")

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected error")
        return _payload(500, "internal_error", "Unexpected internal error.")
