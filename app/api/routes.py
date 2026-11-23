"""REST routes (local demo only; unauthenticated). One transaction per command."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import sessionmaker

from app.api.schemas import (
    BookPage,
    BranchOut,
    CopyOut,
    ErrorOut,
    LoanOut,
    LoanRequestIn,
    LocalLoanRequestIn,
    LocalReturnIn,
    ReturnIn,
    TransferDetail,
    TransitionIn,
)
from app.application import Clock, utc_now
from app.application.activate_loan import activate_loan
from app.application.advance_transfer import advance_transfer
from app.application.local_circulation import create_local_loan, return_local_loan
from app.application.request_loan import request_interlibrary_loan
from app.application.return_loan import return_loan
from app.db import get_session_factory
from app.persistence import queries

router = APIRouter(
    prefix="/api/v1",
    responses={
        404: {"model": ErrorOut, "description": "Resource not found."},
        409: {"model": ErrorOut, "description": "State or idempotency conflict."},
        422: {"model": ErrorOut, "description": "Invalid request."},
        500: {"model": ErrorOut, "description": "Unexpected failure (sanitized)."},
    },
)


def get_clock() -> Clock:
    """Overridable in tests for deterministic timestamps."""
    return utc_now


Factory = Annotated[sessionmaker, Depends(get_session_factory)]
Now = Annotated[Clock, Depends(get_clock)]


# ---- reads ---------------------------------------------------------------------------------


@router.get("/branches", response_model=list[BranchOut], tags=["catalogue"])
def list_branches(factory: Factory):
    with factory() as session:
        return [BranchOut.model_validate(b) for b in queries.list_branches(session)]


@router.get("/books", response_model=BookPage, tags=["catalogue"])
def list_books(
    factory: Factory,
    limit: Annotated[int, Query(ge=1, le=queries.MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with factory() as session:
        books, total = queries.list_books(session, limit=limit, offset=offset)
        return {"items": books, "limit": limit, "offset": offset, "total": total}


@router.get("/copies/{copy_id}", response_model=CopyOut, tags=["catalogue"])
def get_copy(copy_id: int, factory: Factory):
    with factory() as session:
        return CopyOut.model_validate(queries.get_copy(session, copy_id))


@router.get("/loans/{loan_id}", response_model=LoanOut, tags=["loans"])
def get_loan(loan_id: int, factory: Factory):
    with factory() as session:
        return LoanOut.model_validate(queries.get_loan(session, loan_id))


@router.get("/transfers/{transfer_id}", response_model=TransferDetail, tags=["transfers"])
def get_transfer(transfer_id: int, factory: Factory):
    with factory() as session:
        return TransferDetail.model_validate(queries.get_transfer(session, transfer_id))


# ---- commands ------------------------------------------------------------------------------


@router.post(
    "/loans/local",
    response_model=LoanOut,
    status_code=201,
    tags=["loans"],
    summary="Issue an available copy locally (atomic, idempotent)",
    responses={200: {"model": LoanOut, "description": "Idempotent replay"}},
)
def issue_local_loan(
    body: LocalLoanRequestIn,
    response: Response,
    factory: Factory,
    now: Now,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
):
    with factory.begin() as session:
        loan, created = create_local_loan(
            session,
            member_id=body.member_id,
            copy_id=body.copy_id,
            branch_id=body.branch_id,
            idempotency_key=idempotency_key,
            now=now(),
        )
        result = LoanOut.model_validate(loan)
    response.status_code = 201 if created else 200
    return result


@router.post(
    "/loans/{loan_id}/local-return",
    response_model=LoanOut,
    tags=["loans"],
    summary="Check in a local loan at its issuing branch",
)
def check_in_local(
    loan_id: int,
    body: LocalReturnIn,
    factory: Factory,
    now: Now,
):
    with factory.begin() as session:
        loan = return_local_loan(
            session,
            loan_id=loan_id,
            branch_id=body.branch_id,
            condition=body.condition,
            now=now(),
        )
        return LoanOut.model_validate(loan)


@router.post(
    "/loans/interlibrary",
    response_model=LoanOut,
    status_code=201,
    tags=["loans"],
    summary="Request an interlibrary loan (creates the outward transfer atomically)",
    responses={200: {"model": LoanOut, "description": "Idempotent replay of an earlier request."}},
)
def request_loan(
    body: LoanRequestIn,
    response: Response,
    factory: Factory,
    now: Now,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            description="Client-chosen key; same key + same body replays the first result.",
        ),
    ],
):
    with factory.begin() as session:
        loan, created = request_interlibrary_loan(
            session,
            member_id=body.member_id,
            copy_id=body.copy_id,
            destination_branch_id=body.destination_branch_id,
            idempotency_key=idempotency_key,
            now=now(),
        )
        result = LoanOut.model_validate(loan)
    response.status_code = 201 if created else 200
    return result


@router.post(
    "/transfers/{transfer_id}/transitions",
    response_model=TransferDetail,
    tags=["transfers"],
    summary="Advance a transfer to its next legal state",
)
def transition_transfer(transfer_id: int, body: TransitionIn, factory: Factory, now: Now):
    with factory.begin() as session:
        transfer = advance_transfer(
            session, transfer_id=transfer_id, next_status=body.next_status, now=now()
        )
        return TransferDetail.model_validate(transfer)


@router.post(
    "/loans/{loan_id}/activate",
    response_model=LoanOut,
    tags=["loans"],
    summary="Activate a loan after its outward transfer was received",
)
def activate(loan_id: int, factory: Factory, now: Now):
    with factory.begin() as session:
        return LoanOut.model_validate(activate_loan(session, loan_id=loan_id, now=now()))


@router.post(
    "/loans/{loan_id}/return",
    response_model=LoanOut,
    tags=["loans"],
    summary="Borrower returns the copy (GOOD/DAMAGED); creates the return transfer atomically",
)
def give_back(loan_id: int, body: ReturnIn, factory: Factory, now: Now):
    with factory.begin() as session:
        return LoanOut.model_validate(
            return_loan(session, loan_id=loan_id, condition=body.condition, now=now())
        )
