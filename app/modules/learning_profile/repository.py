"""
Mastery Engine module — Repository layer (Phase 14 §8).

Repositories:
  - StudentTopicMasteryRepository: upsert-oriented; supports get-or-create per student×topic.
  - StudentChapterMasteryRepository: upsert for chapter-level aggregation.
  - StudentSubjectMasteryRepository: upsert for subject-level aggregation.
  - MasteryHistoryRepository: append-only; no updates.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.learning_profile.models import (
    MasteryHistory,
    StudentChapterMastery,
    StudentSubjectMastery,
    StudentTopicMastery,
)


class StudentTopicMasteryRepository(BaseRepository[StudentTopicMastery]):
    """Repository for per-student per-topic mastery rows."""

    ALLOWED_SORT_FIELDS = {
        "mastery_score": StudentTopicMastery.mastery_score,
        "attempt_count": StudentTopicMastery.attempt_count,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudentTopicMastery)

    async def get_by_student_topic(
        self, student_id: int, topic_id: int
    ) -> StudentTopicMastery | None:
        """Fetch mastery row for a specific student × topic pair."""
        stmt = (
            select(StudentTopicMastery)
            .where(StudentTopicMastery.student_id == student_id)
            .where(StudentTopicMastery.topic_id == topic_id)
            .where(StudentTopicMastery.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_student(self, student_id: int) -> list[StudentTopicMastery]:
        """Fetch all topic masteries for a student, ordered by mastery_score asc (weakest first)."""
        stmt = (
            select(StudentTopicMastery)
            .where(StudentTopicMastery.student_id == student_id)
            .where(StudentTopicMastery.is_deleted == False)  # noqa: E712
            .order_by(StudentTopicMastery.mastery_score.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_student_subject(
        self, student_id: int, subject_id: int
    ) -> list[StudentTopicMastery]:
        """Fetch topic masteries for a student filtered to one subject."""
        stmt = (
            select(StudentTopicMastery)
            .where(StudentTopicMastery.student_id == student_id)
            .where(StudentTopicMastery.subject_id == subject_id)
            .where(StudentTopicMastery.is_deleted == False)  # noqa: E712
            .order_by(StudentTopicMastery.mastery_score.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_student_chapter(
        self, student_id: int, chapter_id: int
    ) -> list[StudentTopicMastery]:
        """Fetch topic masteries for a student filtered to one chapter."""
        stmt = (
            select(StudentTopicMastery)
            .where(StudentTopicMastery.student_id == student_id)
            .where(StudentTopicMastery.chapter_id == chapter_id)
            .where(StudentTopicMastery.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create(
        self,
        student_id: int,
        topic_id: int,
        chapter_id: int,
        subject_id: int,
    ) -> StudentTopicMastery:
        """Fetch existing mastery row or create a new one initialized to 0.0."""
        existing = await self.get_by_student_topic(student_id, topic_id)
        if existing:
            return existing
        return await self.create(
            {
                "student_id": student_id,
                "topic_id": topic_id,
                "chapter_id": chapter_id,
                "subject_id": subject_id,
                "mastery_score": 0.0,
                "attempt_count": 0,
                "correct_count": 0,
                "last_evaluated_at": None,
            }
        )


class StudentChapterMasteryRepository(BaseRepository[StudentChapterMastery]):
    """Repository for per-student per-chapter mastery rows."""

    ALLOWED_SORT_FIELDS = {
        "mastery_score": StudentChapterMastery.mastery_score,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudentChapterMastery)

    async def get_by_student_chapter(
        self, student_id: int, chapter_id: int
    ) -> StudentChapterMastery | None:
        stmt = (
            select(StudentChapterMastery)
            .where(StudentChapterMastery.student_id == student_id)
            .where(StudentChapterMastery.chapter_id == chapter_id)
            .where(StudentChapterMastery.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_student(self, student_id: int) -> list[StudentChapterMastery]:
        stmt = (
            select(StudentChapterMastery)
            .where(StudentChapterMastery.student_id == student_id)
            .where(StudentChapterMastery.is_deleted == False)  # noqa: E712
            .order_by(StudentChapterMastery.mastery_score.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create(
        self, student_id: int, chapter_id: int, subject_id: int
    ) -> StudentChapterMastery:
        existing = await self.get_by_student_chapter(student_id, chapter_id)
        if existing:
            return existing
        return await self.create(
            {
                "student_id": student_id,
                "chapter_id": chapter_id,
                "subject_id": subject_id,
                "mastery_score": 0.0,
                "topic_count": 0,
                "last_updated_at": None,
            }
        )


class StudentSubjectMasteryRepository(BaseRepository[StudentSubjectMastery]):
    """Repository for per-student per-subject mastery rows."""

    ALLOWED_SORT_FIELDS = {
        "mastery_score": StudentSubjectMastery.mastery_score,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudentSubjectMastery)

    async def get_by_student_subject(
        self, student_id: int, subject_id: int
    ) -> StudentSubjectMastery | None:
        stmt = (
            select(StudentSubjectMastery)
            .where(StudentSubjectMastery.student_id == student_id)
            .where(StudentSubjectMastery.subject_id == subject_id)
            .where(StudentSubjectMastery.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_student(self, student_id: int) -> list[StudentSubjectMastery]:
        stmt = (
            select(StudentSubjectMastery)
            .where(StudentSubjectMastery.student_id == student_id)
            .where(StudentSubjectMastery.is_deleted == False)  # noqa: E712
            .order_by(StudentSubjectMastery.mastery_score.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create(
        self, student_id: int, subject_id: int
    ) -> StudentSubjectMastery:
        existing = await self.get_by_student_subject(student_id, subject_id)
        if existing:
            return existing
        return await self.create(
            {
                "student_id": student_id,
                "subject_id": subject_id,
                "mastery_score": 0.0,
                "chapter_count": 0,
                "last_updated_at": None,
            }
        )


class MasteryHistoryRepository(BaseRepository[MasteryHistory]):
    """Append-only audit trail for mastery updates."""

    ALLOWED_SORT_FIELDS = {
        "evaluated_at": MasteryHistory.evaluated_at,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MasteryHistory)

    async def list_by_student_topic(
        self, student_id: int, topic_id: int
    ) -> list[MasteryHistory]:
        stmt = (
            select(MasteryHistory)
            .where(MasteryHistory.student_id == student_id)
            .where(MasteryHistory.topic_id == topic_id)
            .order_by(MasteryHistory.evaluated_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_evaluation(self, evaluation_id: int) -> list[MasteryHistory]:
        stmt = (
            select(MasteryHistory)
            .where(MasteryHistory.evaluation_id == evaluation_id)
            .order_by(MasteryHistory.evaluated_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
