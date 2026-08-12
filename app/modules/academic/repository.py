"""
Academic module — repository (Phase 8 §19: THE reference pattern every later
module's repository copies).

Read-only snapshot tree - only the ERP sync job (Phase 16/17) mutates these
tables. Every entity repository is now a thin subclass of the generic
`BaseRepository`: it declares `ALLOWED_SORT_FIELDS` (Phase 7 §5.4 whitelist)
and gets soft-delete filtering + `list()`/`get_by_id()` for free.

Caching (Phase 8 §5.5): the Academic Snapshot tree is exactly the "read-heavy,
rarely-changing data" this phase names as the one thing allowed a 60s
in-process TTL cache. `CachedListMixin` wraps `list()` only - `get_by_id`
stays uncached since it's cheap and used for single-row lookups where
freshness matters slightly more.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import AsyncTTLCache
from app.core.db.base_repository import BaseRepository
from app.core.security.rbac import CurrentUser
from app.modules.academic.models import (
    AcademicSession,
    Board,
    Chapter,
    Class,
    School,
    Subject,
    Topic,
    Unit,
)

# One shared cache for the whole snapshot tree - small, rarely-changing
# dataset, so a single 60s TTL cache keyed by (model, args) is enough
# (Phase 8 §5.5), rather than one cache instance per entity type.
_snapshot_cache = AsyncTTLCache(ttl_seconds=60)


class CachedListMixin:
    """Wraps `BaseRepository.list()` with the shared 60s TTL cache. Mixed
    into every Academic entity repository below."""

    async def list(  # type: ignore[override]
        self,
        *,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        current_user: CurrentUser | None = None,
        include_deleted: bool = False,
    ) -> tuple[list, int]:
        scope_key = current_user.school_id if (current_user and current_user.is_school_scoped) else None
        cache_key = (
            self.model.__name__,  # type: ignore[attr-defined]
            tuple(sorted((filters or {}).items())),
            page,
            page_size,
            sort_by,
            sort_dir,
            include_deleted,
            scope_key,
        )

        async def _load() -> tuple[list, int]:
            return await super(CachedListMixin, self).list(  # type: ignore[misc]
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_dir=sort_dir,
                current_user=current_user,
                include_deleted=include_deleted,
            )

        return await _snapshot_cache.get_or_set(cache_key, _load)


class BoardRepository(CachedListMixin, BaseRepository[Board]):
    ALLOWED_SORT_FIELDS = {"name": Board.name, "created_at": Board.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Board)


class SchoolRepository(CachedListMixin, BaseRepository[School]):
    ALLOWED_SORT_FIELDS = {"name": School.name, "created_at": School.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, School)


class AcademicSessionRepository(CachedListMixin, BaseRepository[AcademicSession]):
    ALLOWED_SORT_FIELDS = {
        "start_date": AcademicSession.start_date,
        "name": AcademicSession.name,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AcademicSession)


class ClassRepository(CachedListMixin, BaseRepository[Class]):
    ALLOWED_SORT_FIELDS = {"name": Class.name, "created_at": Class.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Class)


class SubjectRepository(CachedListMixin, BaseRepository[Subject]):
    ALLOWED_SORT_FIELDS = {"name": Subject.name, "created_at": Subject.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Subject)


class ChapterRepository(CachedListMixin, BaseRepository[Chapter]):
    ALLOWED_SORT_FIELDS = {
        "sequence": Chapter.sequence,
        "name": Chapter.name,
        "created_at": Chapter.created_at,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Chapter)


class UnitRepository(CachedListMixin, BaseRepository[Unit]):
    ALLOWED_SORT_FIELDS = {"name": Unit.name, "created_at": Unit.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Unit)


class TopicRepository(CachedListMixin, BaseRepository[Topic]):
    ALLOWED_SORT_FIELDS = {"name": Topic.name, "created_at": Topic.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Topic)
