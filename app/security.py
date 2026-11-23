"""Fail-closed RS256 bearer verification and server-side branch grants.

The planned Next.js BFF will mint short-lived audience tokens after validating
its own login session. The backend holds only PUBLIC JWKS, never a private key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import Branch, StaffBranchGrant, StaffUser

bearer = HTTPBearer(auto_error=False)
WRITE_ROLES = frozenset({"LIBRARIAN", "BRANCH_MANAGER", "NETWORK_ADMIN"})
READ_ROLES = WRITE_ROLES | {"VIEWER"}
MAX_TOKEN_SECONDS = 300


@dataclass(frozen=True)
class StaffGrant:
    subject: str
    branch_id: int
    role: str


def require_legacy_local_api() -> None:
    """V1 is never available by default, and cannot be exposed on known managed hosts."""
    if (
        os.getenv("LIBRARY_RUNTIME_MODE") == "local"
        and os.getenv("LIBRARY_ENABLE_UNSAFE_V1") == "1"
        and not any(
            os.getenv(name)
            for name in ("VERCEL", "K_SERVICE", "RENDER", "RAILWAY_ENVIRONMENT", "DYNO")
        )
    ):
        return
    raise HTTPException(status_code=404, detail="Not found")


def _auth_error() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid or missing bearer token")


def verified_subject(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    """Validate signature, algorithm, audience, issuer, time window and subject."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _auth_error()

    token = credentials.credentials
    if len(token) > 8192:
        raise _auth_error()

    issuer = os.getenv("LIBRARY_JWT_ISSUER")
    audience = os.getenv("LIBRARY_JWT_AUDIENCE")
    public_jwks = os.getenv("LIBRARY_JWKS_JSON")
    if not issuer or not audience or not public_jwks:
        raise HTTPException(status_code=503, detail="Authentication not configured")

    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise _auth_error()
        kid = header.get("kid")
        if not isinstance(kid, str) or not (1 <= len(kid) <= 128):
            raise _auth_error()
        keyset = jwt.PyJWKSet.from_json(public_jwks)
        matching = [key for key in keyset.keys if key.key_id == kid and key.key_type == "RSA"]
        if len(matching) != 1:
            raise _auth_error()
        claims = jwt.decode(
            token,
            matching[0].key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["iss", "aud", "sub", "exp", "iat", "nbf"]},
        )
        issued = claims["iat"]
        expires = claims["exp"]
        subject = claims["sub"]
        now = datetime.now(UTC).timestamp()
        if (
            not isinstance(subject, str)
            or not (1 <= len(subject) <= 180)
            or not isinstance(issued, int)
            or isinstance(issued, bool)
            or not isinstance(expires, int)
            or isinstance(expires, bool)
            or expires - issued > MAX_TOKEN_SECONDS
            or expires <= issued
            or issued > now + 30
        ):
            raise _auth_error()
        return subject
    except HTTPException:
        raise
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise _auth_error() from exc


def branch_grant(session: Session, subject: str, branch_id: int, *, write: bool) -> StaffGrant:
    """Require active user, active branch, active grant and appropriate database role."""
    role = session.execute(
        select(StaffBranchGrant.role)
        .join(StaffUser, StaffUser.id == StaffBranchGrant.staff_user_id)
        .join(Branch, Branch.id == StaffBranchGrant.branch_id)
        .where(
            StaffUser.subject == subject,
            StaffUser.active.is_(True),
            StaffBranchGrant.branch_id == branch_id,
            StaffBranchGrant.active.is_(True),
            Branch.active.is_(True),
        )
    ).scalar_one_or_none()
    permitted = WRITE_ROLES if write else READ_ROLES
    if role not in permitted:
        raise HTTPException(status_code=403, detail="Insufficient branch permission")
    return StaffGrant(subject=subject, branch_id=branch_id, role=role)
