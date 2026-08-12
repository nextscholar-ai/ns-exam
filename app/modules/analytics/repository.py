"""
Analytics Engine module — Repository layer (Phase 16 §8).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.analytics.models import ClassAnalyticsSummary, StudentAnalyticsSummary


class StudentAnalyticsSummaryRepository(BaseRepository[StudentAnalyticsSummary]):
    """Repository for student analytics summaries."""

    ALLOWED_SORT_FIELDS = {
        "overall_mastery": StudentAnalyticsSummary.overall_mastery,
        "average_percentage": StudentAnalyticsSummary.average_percentage,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudentAnalyticsSummary)

    async def get_by_student_subject(
        self, student_id: int, subject_id: int
    ) -> StudentAnalyticsSummary | None:
        stmt = (
            select(StudentAnalyticsSummary)
            .where(StudentAnalyticsSummary.student_id == student_id)
            .where(StudentAnalyticsSummary.subject_id == subject_id)
            .where(StudentAnalyticsSummary.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ClassAnalyticsSummaryRepository(BaseRepository[ClassAnalyticsSummary]):
    """Repository for class analytics summaries."""

    ALLOWED_SORT_FIELDS = {
        "class_average_score": ClassAnalyticsSummary.class_average_score,
        "pass_percentage": ClassAnalyticsSummary.pass_percentage,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ClassAnalyticsSummary)

    async def get_by_class_exam(
        self, class_id: int, exam_id: int
    ) -> ClassAnalyticsSummary | None:
        stmt = (
            select(ClassAnalyticsSummary)
            .where(ClassAnalyticsSummary.class_id == class_id)
            .where(ClassAnalyticsSummary.exam_id == exam_id)
            .where(ClassAnalyticsSummary.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
