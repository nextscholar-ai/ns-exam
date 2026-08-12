"""
`BaseRepository[ModelType]` (Phase 8 §5.1) — the generic contract every
module's `repository.py` inherits.

Two guarantees are structural here, not left to developer memory:
  1. Every query automatically filters `is_deleted = false` unless the caller
     explicitly passes `include_deleted=True` (admin/audit views only).
  2. Every query automatically applies row-level School/Board scoping when a
     school-scoped `current_user` (TEACHER/SCHOOL_ADMIN, per Phase 6 §6.4) is
     passed - via the overridable `_apply_scope()` hook. SUPER_ADMIN/ADMIN
     bypass it. This is the primary structural defense against IDOR
     (Phase 8 §9): a school-scoped caller requesting a row outside their
     school gets a 404 (via `get_by_id` returning None), never a 403 that
     would leak existence.
"""
from __future__ import annotations

import time
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.db.base_model import Base
from app.core.exceptions import NotFoundError, ValidationDomainError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser

logger = get_logger(__name__)

ModelT = TypeVar("ModelT", bound=Base)

SLOW_QUERY_THRESHOLD_MS = 500  # Phase 8 §12


class BaseRepository(Generic[ModelT]):
    """
    Usage:
        class QuestionRepository(BaseRepository[Question]):
            def __init__(self, session: AsyncSession) -> None:
                super().__init__(session, Question)

    Subclasses override `ALLOWED_SORT_FIELDS` (whitelist, Phase 7 §5.4) and
    `_apply_scope()` when their model's scoping path differs from the default
    `school_id` column (e.g. Question Bank scopes by `board_id` only,
    Phase 8 §5.1).
    """

    ALLOWED_SORT_FIELDS: dict[str, InstrumentedAttribute] = {}

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    # ---------------------------------------------------------------- read --
    async def get_by_id(
        self,
        id_: int,
        *,
        current_user: CurrentUser | None = None,
        include_deleted: bool = False,
    ) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == id_)
        stmt = self._apply_soft_delete_filter(stmt, include_deleted)
        stmt = self._apply_scope(stmt, current_user)
        return await self._execute_one("get_by_id", stmt)

    async def get_by_public_id(
        self,
        public_id: UUID,
        *,
        current_user: CurrentUser | None = None,
        include_deleted: bool = False,
    ) -> ModelT | None:
        stmt = select(self.model).where(self.model.public_id == public_id)
        stmt = self._apply_soft_delete_filter(stmt, include_deleted)
        stmt = self._apply_scope(stmt, current_user)
        return await self._execute_one("get_by_public_id", stmt)

    async def list(
        self,
        *,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        current_user: CurrentUser | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[ModelT], int]:
        """
        Generic list/search. `filters` is a dict of column-name -> value,
        applied as plain equality where clauses for any key that is both a
        real mapped column on `self.model` AND explicitly declared safe
        (present in the model's columns) - module repositories with richer
        query needs (range filters, joins, keyword search) override this or
        add dedicated methods (Phase 8 §5.2), still going through the same
        soft-delete + scoping base.
        """
        stmt = select(self.model)
        stmt = self._apply_soft_delete_filter(stmt, include_deleted)
        stmt = self._apply_scope(stmt, current_user)
        stmt = self._apply_filters(stmt, filters or {})

        total = await self._count(stmt)

        stmt = self._apply_sorting(stmt, sort_by, sort_dir)
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)

        start = time.perf_counter()
        result = await self.session.execute(stmt)
        self._log_if_slow("list", start)
        return list(result.scalars().all()), total

    # --------------------------------------------------------------- write --
    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    async def create(self, obj_in: dict[str, Any]) -> ModelT:
        instance = self.model(**obj_in)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(
        self, id_: int, obj_in: dict[str, Any], *, current_user: CurrentUser | None = None
    ) -> ModelT:
        instance = await self.get_by_id(id_, current_user=current_user)
        if instance is None:
            raise NotFoundError(f"{self.model.__name__} with id {id_} not found")
        for key, value in obj_in.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance

    async def soft_delete(
        self, id_: int, deleted_by: int, *, current_user: CurrentUser | None = None
    ) -> None:
        instance = await self.get_by_id(id_, current_user=current_user)
        if instance is None:
            raise NotFoundError(f"{self.model.__name__} with id {id_} not found")
        instance.mark_deleted(deleted_by)
        await self.session.flush()

    async def hard_delete(self, id_: int) -> None:
        """ONLY used by the Guest cleanup job (Phase 1 §13) - never exposed
        through a normal service/router code path."""
        stmt = delete(self.model).where(self.model.id == id_)
        await self.session.execute(stmt)

    async def flush(self) -> None:
        await self.session.flush()

    # ------------------------------------------------------------- hooks ---
    def _apply_soft_delete_filter(self, stmt: Select, include_deleted: bool) -> Select:
        if include_deleted:
            return stmt
        return stmt.where(self.model.is_deleted.is_(False))

    def _apply_scope(self, stmt: Select, current_user: CurrentUser | None) -> Select:
        """
        Default scoping: filters by `school_id` when `current_user` is
        school-scoped (Phase 6 §6.4 / Phase 8 §5.1). Override in a module
        repository whose model scopes differently (e.g. board-level only) or
        has no scoping column at all (snapshot/reference tables).
        """
        if current_user is None or not current_user.is_school_scoped:
            return stmt
        if not hasattr(self.model, "school_id"):
            return stmt
        return stmt.where(self.model.school_id == current_user.school_id)

    def _apply_filters(self, stmt: Select, filters: dict[str, Any]) -> Select:
        for key, value in filters.items():
            if value is None:
                continue
            column = getattr(self.model, key, None)
            if column is None:
                raise ValidationDomainError(f"'{key}' is not a filterable field on {self.model.__name__}")
            stmt = stmt.where(column == value)
        return stmt

    def _apply_sorting(self, stmt: Select, sort_by: str | None, sort_dir: str) -> Select:
        if not self.ALLOWED_SORT_FIELDS:
            return stmt
        default_field = next(iter(self.ALLOWED_SORT_FIELDS))
        key = sort_by or default_field
        column = self.ALLOWED_SORT_FIELDS.get(key)
        if column is None:
            allowed = ", ".join(sorted(self.ALLOWED_SORT_FIELDS))
            raise ValidationDomainError(f"Cannot sort by '{key}'. Allowed fields: {allowed}")
        return stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    # ------------------------------------------------------------- utils ---
    async def _count(self, stmt: Select) -> int:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return (await self.session.execute(count_stmt)).scalar_one()

    async def _execute_one(self, query_name: str, stmt: Select) -> ModelT | None:
        start = time.perf_counter()
        result = await self.session.execute(stmt)
        self._log_if_slow(query_name, start)
        return result.scalar_one_or_none()

    def _log_if_slow(self, query_name: str, start_perf_counter: float) -> None:
        elapsed_ms = (time.perf_counter() - start_perf_counter) * 1000
        if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
            # Phase 8 §12: log the query name + filters, never raw SQL with
            # bound data, to avoid leaking PII into logs.
            logger.warning(
                "repository.slow_query",
                model=self.model.__name__,
                query=query_name,
                elapsed_ms=round(elapsed_ms, 1),
            )
