"""Operational read-only catalogue API. All counts come from PostgreSQL."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from app.db import get_session_factory
from app.persistence.catalog import search_catalog

router = APIRouter(prefix="/api/v1/catalog", tags=["catalogue"])


class CatalogItem(BaseModel):
    id: int
    isbn: str
    title: str
    author: str
    total_copies: int
    available_copies: int


class CatalogPage(BaseModel):
    items: list[CatalogItem]
    total: int
    limit: int
    offset: int


@router.get("/search", response_model=CatalogPage)
def find_books(
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    branch_id: Annotated[int | None, Query(ge=1)] = None,
    available_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Search title, author and ISBN; optionally narrow availability by branch."""
    with factory() as session:
        return search_catalog(
            session,
            q=q,
            branch_id=branch_id,
            available_only=available_only,
            limit=limit,
            offset=offset,
        )
