"""
Student Profile module — repository (Phase 4 §6.3).

Read access to `StudentProfile`. `list_active_by_school` is used by the
nightly analytics recompute job (`app/jobs/tasks.py`) and the ERP inbound
snapshot sync.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.student.models import StudentProfile


class StudentRepository(BaseRepository[StudentProfile]):
    ALLOWED_SORT_FIELDS = {
        "name": StudentProfile.name,
        "created_at": StudentProfile.created_at,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudentProfile)

    async def list_active_by_school(self, school_id: int) -> list[StudentProfile]:
        """Active, non-deleted student profiles for a school (snapshot sync / jobs)."""
        stmt = (
            select(StudentProfile)
            .where(StudentProfile.school_id == school_id)
            .where(StudentProfile.is_deleted.is_(False))
            .where(StudentProfile.status == "ACTIVE")
            .order_by(StudentProfile.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
