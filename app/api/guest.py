"""Anonymous guest operations on isolated, synthetic PostgreSQL workspaces.

Every request requires a short-lived BFF-signed guest:UUIDv4 bearer token.
The visitor has no login; the browser never receives the API bearer token.
NO public deployment without creation rate limits, expiry cleanup and CSRF QA.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import sessionmaker

from app.api.schemas import LoanOut, LocalLoanRequestIn, LocalReturnIn
from app.application import utc_now
from app.application.guest_workspace import (
    ensure_guest_loan_quota,
    guest_workspace,
    owned_branch,
    owned_copy,
    owned_loan,
    owned_member,
    start_guest_workspace,
)
from app.application.local_circulation import create_local_loan, return_local_loan
from app.db import get_session_factory
from app.domain.states import CopyStatus
from app.persistence.models import (
    Book,
    Branch,
    Copy,
    DemoWorkspaceBranch,
    DemoWorkspaceMember,
    Member,
)
from app.persistence.overview import get_branch_overview
from app.security import verified_subject

router = APIRouter(prefix="/api/v2/guest", tags=["guest"])
Subject = Annotated[str, Depends(verified_subject)]
Factory = Annotated[sessionmaker, Depends(get_session_factory)]


class GuestBranch(BaseModel):
    branch_id: int
    name: str


class GuestProfile(BaseModel):
    expires_at: str
    branches: list[GuestBranch]


class GuestBook(BaseModel):
    id: int
    title: str
    author: str
    isbn: str
    total_copies: int
    available_copies: int


class GuestCatalog(BaseModel):
    items: list[GuestBook]
    total: int
    limit: int
    offset: int


class GuestCopy(BaseModel):
    id: int
    code: str
    title: str
    author: str
    status: str
    physical_condition: str


class GuestCopies(BaseModel):
    items: list[GuestCopy]
    total: int


class GuestMember(BaseModel):
    id: int
    code: str
    enabled: bool


def _profile(session, workspace) -> dict:
    rows = session.execute(
        select(DemoWorkspaceBranch.branch_id, Branch.name)
        .join(Branch, Branch.id == DemoWorkspaceBranch.branch_id)
        .where(DemoWorkspaceBranch.workspace_id == workspace.id)
        .order_by(DemoWorkspaceBranch.branch_id)
    ).all()
    return {
        "expires_at": workspace.expires_at.isoformat(),
        "branches": [{"branch_id": bid, "name": name} for bid, name in rows],
    }


@router.post("/start", response_model=GuestProfile, status_code=201)
def start_demo(response: Response, subject: Subject, factory: Factory):
    with factory.begin() as session:
        workspace, created = start_guest_workspace(session, subject=subject, now=utc_now())
        result = _profile(session, workspace)
    response.status_code = 201 if created else 200
    return result


@router.get("/me", response_model=GuestProfile)
def my_demo(subject: Subject, factory: Factory):
    with factory() as session:
        return _profile(session, guest_workspace(session, subject, utc_now()))


@router.get("/branches/{branch_id}/overview")
def guest_overview(branch_id: int, subject: Subject, factory: Factory):
    now = utc_now()
    with factory() as session:
        workspace = guest_workspace(session, subject, now)
        owned_branch(session, workspace, branch_id)
        return get_branch_overview(session, branch_id=branch_id, now=now)


@router.get("/branches/{branch_id}/catalog", response_model=GuestCatalog)
def guest_catalog(
    branch_id: int,
    subject: Subject,
    factory: Factory,
    q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    available_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with factory() as session:
        workspace = guest_workspace(session, subject, utc_now())
        owned_branch(session, workspace, branch_id)
        available = func.count(Copy.id).filter(Copy.status == CopyStatus.AVAILABLE.value)
        statement = (
            select(
                Book.id,
                Book.title,
                Book.author,
                Book.isbn,
                func.count(Copy.id).label("total_copies"),
                available.label("available_copies"),
            )
            .join(Copy, Copy.book_id == Book.id)
            .where(
                Copy.current_branch_id == branch_id,
                Copy.owning_branch_id == branch_id,
            )
            .group_by(Book.id, Book.title, Book.author, Book.isbn)
        )
        if q:
            statement = statement.where(
                or_(
                    Book.title.icontains(q, autoescape=True),
                    Book.author.icontains(q, autoescape=True),
                    Book.isbn.icontains(q, autoescape=True),
                )
            )
        if available_only:
            statement = statement.having(available > 0)
        total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = session.execute(
            statement.order_by(Book.title, Book.id).limit(limit).offset(offset)
        ).mappings()
        return {
            "items": [dict(item) for item in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/branches/{branch_id}/copies", response_model=GuestCopies)
def guest_copies(
    branch_id: int,
    subject: Subject,
    factory: Factory,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
):
    with factory() as session:
        workspace = guest_workspace(session, subject, utc_now())
        owned_branch(session, workspace, branch_id)
        stmt = (
            select(
                Copy.id,
                Copy.code,
                Book.title,
                Book.author,
                Copy.status,
                Copy.physical_condition,
            )
            .join(Book, Book.id == Copy.book_id)
            .where(
                Copy.current_branch_id == branch_id,
                Copy.owning_branch_id == branch_id,
            )
        )
        if q:
            stmt = stmt.where(
                or_(
                    Copy.code.icontains(q, autoescape=True),
                    Book.title.icontains(q, autoescape=True),
                    Book.author.icontains(q, autoescape=True),
                )
            )
        rows = session.execute(stmt.order_by(Book.title, Copy.code).limit(50)).mappings()
        items = [dict(item) for item in rows]
        return {"items": items, "total": len(items)}


@router.get("/members", response_model=list[GuestMember])
def guest_members(subject: Subject, factory: Factory):
    with factory() as session:
        workspace = guest_workspace(session, subject, utc_now())
        rows = session.execute(
            select(Member.id, Member.code, Member.enabled)
            .join(DemoWorkspaceMember, DemoWorkspaceMember.member_id == Member.id)
            .where(DemoWorkspaceMember.workspace_id == workspace.id)
            .order_by(Member.code)
            .limit(10)
        ).mappings()
        return [dict(item) for item in rows]


@router.get("/loans/{loan_id}", response_model=LoanOut)
def guest_loan(loan_id: int, subject: Subject, factory: Factory):
    with factory() as session:
        workspace = guest_workspace(session, subject, utc_now())
        return LoanOut.model_validate(owned_loan(session, workspace, loan_id))


@router.post("/loans/local", response_model=LoanOut, status_code=201)
def guest_issue(
    body: LocalLoanRequestIn,
    response: Response,
    subject: Subject,
    factory: Factory,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
):
    with factory.begin() as session:
        workspace = guest_workspace(session, subject, utc_now(), lock=True)
        owned_branch(session, workspace, body.branch_id)
        owned_member(session, workspace, body.member_id)
        owned_copy(session, body.branch_id, body.copy_id)
        scoped_key = sha256(
            f"guest:{subject}:{body.branch_id}:{idempotency_key}".encode()
        ).hexdigest()
        ensure_guest_loan_quota(session, workspace=workspace, scoped_key=scoped_key)
        loan, created = create_local_loan(
            session,
            member_id=body.member_id,
            copy_id=body.copy_id,
            branch_id=body.branch_id,
            idempotency_key=scoped_key,
            now=utc_now(),
        )
        result = LoanOut.model_validate(loan)
    response.status_code = 201 if created else 200
    return result


@router.post("/loans/{loan_id}/local-return", response_model=LoanOut)
def guest_return(
    loan_id: int,
    body: LocalReturnIn,
    subject: Subject,
    factory: Factory,
):
    with factory.begin() as session:
        workspace = guest_workspace(session, subject, utc_now(), lock=True)
        loan = owned_loan(session, workspace, loan_id)
        owned_branch(session, workspace, body.branch_id)
        if loan.destination_branch_id != body.branch_id:
            raise HTTPException(status_code=404, detail="Loan not found")
        result = return_local_loan(
            session,
            loan_id=loan_id,
            branch_id=body.branch_id,
            condition=body.condition,
            now=utc_now(),
        )
        return LoanOut.model_validate(result)
