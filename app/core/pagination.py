"""
Shared pagination + sorting contract (Phase 7 §5.4), used by every module's
list endpoint so behaviour is consistent across the whole platform.

`page`/`page_size` (capped at MAX_PAGE_SIZE) and `sort_by`/`sort_dir` are the
only generic query params. Module-specific filters (board_id, subject_id,
status, ...) are always explicit typed query params on that module's own
router function — never a generic free-form filter language (Phase 7 §5.4).
"""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import ValidationDomainError
from app.shared.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

T = TypeVar("T")


class SortParams(BaseModel):
    sort_by: str | None = None
    sort_dir: str = Field("asc", pattern="^(asc|desc)$")


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination_query(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    """FastAPI dependency: `params: PageParams = Depends(pagination_query)`."""
    return PageParams(page=page, page_size=page_size)


def sorting_query(
    sort_by: str | None = Query(None),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
) -> SortParams:
    """FastAPI dependency: `sort: SortParams = Depends(sorting_query)`."""
    return SortParams(sort_by=sort_by, sort_dir=sort_dir)


def apply_sorting(
    stmt: Select,
    model: type,
    sort: SortParams,
    allowed_fields: dict[str, InstrumentedAttribute],
    *,
    default_field: str,
) -> Select:
    """
    Applies `ORDER BY` against a whitelist only - never raw column injection
    from client input (Phase 7 §5.4). `allowed_fields` maps the public sort
    key (what the client sends) to the actual mapped column.
    """
    sort_by = sort.sort_by or default_field
    column = allowed_fields.get(sort_by)
    if column is None:
        allowed = ", ".join(sorted(allowed_fields))
        raise ValidationDomainError(
            f"Cannot sort by '{sort_by}'. Allowed fields: {allowed}"
        )
    return stmt.order_by(column.desc() if sort.sort_dir == "desc" else column.asc())


class Page(BaseModel, Generic[T]):
    """
    Internal shape a service/repository returns. The response-envelope
    middleware (Phase 7 §5.2) unwraps this into the documented
    `{"success": true, "data": [...], "meta": {page, page_size, total, ...}}`
    shape automatically - routers just return a `Page[...]` like any other
    schema.
    """

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)
