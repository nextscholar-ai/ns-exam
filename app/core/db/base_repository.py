"""
Generic base repository - all DB access lives behind repository classes,
never called directly from services (Phase 5 §7 layering rule).

Phase 8 (Repository Layer) will extend this with pagination, filtering, and
per-module query methods. This module provides the foundation used from
Phase 1 onward so every module's repository has a consistent contract.
"""
from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_model import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Generic CRUD repository, parameterized by ORM model.

    Usage:
        class QuestionRepository(BaseRepository[Question]):
            def __init__(self, session: AsyncSession) -> None:
                super().__init__(session, Question)
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, id_: int, *, include_deleted: bool = False) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == id_)
        if not include_deleted:
            stmt = stmt.where(self.model.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_id(
        self, public_id: UUID, *, include_deleted: bool = False
    ) -> ModelT | None:
        stmt = select(self.model).where(self.model.public_id == public_id)
        if not include_deleted:
            stmt = stmt.where(self.model.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self, *, limit: int = 50, offset: int = 0, include_deleted: bool = False
    ) -> list[ModelT]:
        stmt = select(self.model)
        if not include_deleted:
            stmt = stmt.where(self.model.is_deleted.is_(False))
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    async def flush(self) -> None:
        """Push pending changes to DB without committing (needed to get generated id)."""
        await self.session.flush()

    async def soft_delete(self, instance: ModelT, *, actor_user_id: int) -> None:
        instance.mark_deleted(actor_user_id)
        await self.flush()
