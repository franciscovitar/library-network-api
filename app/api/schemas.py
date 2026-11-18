"""Pydantic request/response models. Requests forbid unknown fields (no mass assignment)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.states import PhysicalCondition, TransferStatus


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoanRequestIn(_In):
    member_id: int = Field(ge=1, examples=[1])
    copy_id: int = Field(ge=1, examples=[1])
    destination_branch_id: int = Field(ge=1, examples=[2])


class TransitionIn(_In):
    next_status: TransferStatus = Field(examples=["DISPATCHED"])


class ReturnIn(_In):
    condition: PhysicalCondition = Field(examples=["GOOD"])


class BranchOut(_Out):
    id: int
    name: str
    active: bool


class BookOut(_Out):
    id: int
    isbn: str
    title: str
    author: str


class BookPage(BaseModel):
    items: list[BookOut]
    limit: int
    offset: int
    total: int


class CopyOut(_Out):
    id: int
    code: str
    book_id: int
    owning_branch_id: int
    current_branch_id: int
    status: str
    physical_condition: str


class TransferEventOut(_Out):
    id: int
    from_status: str | None
    to_status: str
    occurred_at: datetime


class TransferSummary(_Out):
    id: int
    loan_id: int
    direction: str
    origin_branch_id: int
    destination_branch_id: int
    status: str
    created_at: datetime
    received_at: datetime | None


class TransferDetail(TransferSummary):
    events: list[TransferEventOut]


class LoanOut(_Out):
    id: int
    member_id: int
    copy_id: int
    origin_branch_id: int
    destination_branch_id: int
    status: str
    requested_at: datetime
    started_at: datetime | None
    due_at: datetime | None
    borrower_returned_at: datetime | None
    closed_at: datetime | None
    return_condition: str | None
    transfers: list[TransferSummary]


class ErrorBody(BaseModel):
    code: str = Field(examples=["copy_not_available"])
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody
