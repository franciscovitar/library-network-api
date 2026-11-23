"""Authenticated staff routes, independent of the loopback-only legacy API."""

from __future__ import annotations

from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import sessionmaker

from app.api.catalog import CatalogPage
from app.api.schemas import LoanOut, LocalLoanRequestIn, LocalReturnIn
from app.application import utc_now
from app.application.local_circulation import create_local_loan, return_local_loan
from app.db import get_session_factory
from app.persistence.catalog import search_catalog
from app.persistence.models import Book, Branch, Copy, Loan, Member, StaffBranchGrant, StaffUser
from app.persistence.overview import get_branch_overview
from app.security import branch_grant, verified_subject

router = APIRouter(prefix="/api/v2", tags=["staff"])


class BranchAccess(BaseModel):
    branch_id: int
    branch_name: str
    role: str


class StaffProfile(BaseModel):
    branches: list[BranchAccess]


def _scope_key(subject: str, branch_id: int, key: str) -> str:
    """A retry cannot replay a different staff user's successful request."""
    return sha256(f"local:{subject}:{branch_id}:{key}".encode()).hexdigest()


class BranchOverview(BaseModel):
    branch_id: int
    total_copies: int
    available_copies: int
    catalog_titles: int
    active_loans: int
    overdue_loans: int
    pending_returns: int
    pending_arrivals: int
    pending_dispatches: int


@router.get("/branches/{branch_id}/overview", response_model=BranchOverview)
def branch_overview(
    branch_id: int,
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
):
    """Live branch metrics; every value is computed from the current database state."""
    with factory() as session:
        branch_grant(session, subject, branch_id, write=False)
        return get_branch_overview(session, branch_id=branch_id, now=utc_now())


class StaffCopy(BaseModel):
    id: int
    code: str
    book_id: int
    title: str
    author: str
    isbn: str
    status: str
    physical_condition: str


class StaffCopyPage(BaseModel):
    items: list[StaffCopy]
    total: int
    limit: int
    offset: int


class MemberLookup(BaseModel):
    id: int
    code: str
    enabled: bool


@router.get("/branches/{branch_id}/copies", response_model=StaffCopyPage)
def branch_copies(
    branch_id: int,
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Only copies owned by and currently located at this authorized branch."""
    with factory() as session:
        branch_grant(session, subject, branch_id, write=False)
        stmt = (
            select(
                Copy.id,
                Copy.code,
                Copy.book_id,
                Book.title,
                Book.author,
                Book.isbn,
                Copy.status,
                Copy.physical_condition,
            )
            .join(Book, Book.id == Copy.book_id)
            .where(
                Copy.current_branch_id == branch_id,
                Copy.owning_branch_id == branch_id,
            )
        )
        if q is not None:
            stmt = stmt.where(
                or_(
                    Copy.code.icontains(q, autoescape=True),
                    Book.title.icontains(q, autoescape=True),
                    Book.author.icontains(q, autoescape=True),
                    Book.isbn.icontains(q, autoescape=True),
                )
            )
        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.execute(
            stmt.order_by(Book.title, Copy.code, Copy.id).limit(limit).offset(offset)
        ).mappings()
        return {"items": [dict(row) for row in rows], "total": total,
                "limit": limit, "offset": offset}


@router.get("/branches/{branch_id}/members/lookup", response_model=MemberLookup)
def member_lookup(
    branch_id: int,
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    code: Annotated[str, Query(min_length=1, max_length=32)],
):
    """Exact-match synthetic member lookup; no list or PII enumeration API."""
    with factory() as session:
        branch_grant(session, subject, branch_id, write=False)
        member = session.scalar(select(Member).where(Member.code == code.strip()))
        if member is None:
            raise HTTPException(status_code=404, detail="Member not found")
        return MemberLookup.model_validate(member, from_attributes=True)


@router.get("/me", response_model=StaffProfile)
def my_access(
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
):
    with factory() as session:
        rows = session.execute(
            select(StaffBranchGrant.branch_id, Branch.name, StaffBranchGrant.role)
            .join(StaffUser, StaffUser.id == StaffBranchGrant.staff_user_id)
            .join(Branch, Branch.id == StaffBranchGrant.branch_id)
            .where(
                StaffUser.subject == subject,
                StaffUser.active.is_(True),
                StaffBranchGrant.active.is_(True),
                Branch.active.is_(True),
            )
            .order_by(Branch.name, StaffBranchGrant.branch_id)
        ).all()
        return {
            "branches": [
                {"branch_id": branch_id, "branch_name": name, "role": role}
                for branch_id, name, role in rows
            ]
        }


@router.get("/catalog/search", response_model=CatalogPage)
def secure_catalog(
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    branch_id: Annotated[int, Query(ge=1)],
    q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    available_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with factory() as session:
        branch_grant(session, subject, branch_id, write=False)
        return search_catalog(
            session,
            q=q,
            branch_id=branch_id,
            available_only=available_only,
            limit=limit,
            offset=offset,
        )


@router.get("/loans/{loan_id}", response_model=LoanOut)
def secure_loan(
    loan_id: int,
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
):
    with factory() as session:
        loan = session.get(Loan, loan_id)
        if loan is None:
            raise HTTPException(status_code=404, detail="Loan not found")
        try:
            branch_grant(session, subject, loan.destination_branch_id, write=False)
        except HTTPException as exc:
            raise HTTPException(status_code=404, detail="Loan not found") from exc
        return LoanOut.model_validate(loan)


@router.post("/loans/local", status_code=201, response_model=LoanOut)
def secure_issue(
    body: LocalLoanRequestIn,
    response: Response,
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
):
    with factory.begin() as session:
        branch_grant(session, subject, body.branch_id, write=True)
        loan, created = create_local_loan(
            session,
            member_id=body.member_id,
            copy_id=body.copy_id,
            branch_id=body.branch_id,
            idempotency_key=_scope_key(subject, body.branch_id, idempotency_key),
            now=utc_now(),
        )
        result = LoanOut.model_validate(loan)
    response.status_code = 201 if created else 200
    return result


@router.post("/loans/{loan_id}/local-return", response_model=LoanOut)
def secure_return(
    loan_id: int,
    body: LocalReturnIn,
    subject: Annotated[str, Depends(verified_subject)],
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
):
    with factory.begin() as session:
        loan = session.get(Loan, loan_id)
        if loan is None:
            raise HTTPException(status_code=404, detail="Loan not found")
        try:
            branch_grant(session, subject, loan.destination_branch_id, write=True)
        except HTTPException as exc:
            raise HTTPException(status_code=404, detail="Loan not found") from exc
        if loan.destination_branch_id != body.branch_id:
            raise HTTPException(status_code=409, detail="Return branch does not match loan")
        result = return_local_loan(
            session,
            loan_id=loan_id,
            branch_id=body.branch_id,
            condition=body.condition,
            now=utc_now(),
        )
        return LoanOut.model_validate(result)
