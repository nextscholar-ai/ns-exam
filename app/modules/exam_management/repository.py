"""
Exam Management module — Repository layer (Phase 12).

Provides specialized repositories inheriting `BaseRepository[ModelT]`:
  - `ExamRepository`
  - `ExamStatusHistoryRepository`
  - `ExamStudentAssignmentRepository`
  - `StudentAttemptRepository`

Enforces strict state machine validation during status updates.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.core.security.rbac import CurrentUser
from app.modules.exam_management.domain.state_machine import validate_transition
from app.modules.exam_management.models import (
    Exam,
    ExamStatusHistory,
    ExamStudentAssignment,
    StudentAttempt,
)


class ExamRepository(BaseRepository[Exam]):
    """Repository for Exam aggregate root."""

    ALLOWED_SORT_FIELDS = {
        "created_at": Exam.created_at,
        "title": Exam.title,
        "status": Exam.status,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Exam)

    async def transition_status(
        self,
        exam_id: int,
        target_status: str,
        actor_id: int | None = None,
    ) -> Exam:
        """
        The ONLY authoritative way to transition an Exam's status.
        Validates transition via state_machine.py and appends to ExamStatusHistory.
        """
        exam = await self.get_or_raise(exam_id)
        current_status = exam.status

        # Validate transition via domain state machine
        validate_transition(current_status, target_status)

        # Update exam status
        exam.status = target_status
        now = datetime.now(tz=timezone.utc)
        if target_status == "ACTIVE" and exam.actual_start_at is None:
            exam.actual_start_at = now
        elif target_status == "COMPLETED" and exam.actual_end_at is None:
            exam.actual_end_at = now
        elif target_status == "PUBLISHED" and exam.published_at is None:
            exam.published_at = now
            if actor_id:
                exam.published_by = actor_id

        # Write to append-only history table
        history_entry = ExamStatusHistory(
            exam_id=exam.id,
            from_status=current_status,
            to_status=target_status,
            changed_by=actor_id,
            changed_at=now,
        )
        self.session.add(history_entry)
        await self.session.flush()

        return exam


class ExamStatusHistoryRepository(BaseRepository[ExamStatusHistory]):
    """Repository for ExamStatusHistory append-only log."""

    ALLOWED_SORT_FIELDS = {"changed_at": ExamStatusHistory.changed_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExamStatusHistory)

    async def list_by_exam(self, exam_id: int) -> list[ExamStatusHistory]:
        stmt = (
            select(ExamStatusHistory)
            .where(ExamStatusHistory.exam_id == exam_id)
            .order_by(ExamStatusHistory.changed_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ExamStudentAssignmentRepository(BaseRepository[ExamStudentAssignment]):
    """Repository for ExamStudentAssignment links."""

    ALLOWED_SORT_FIELDS = {"assigned_at": ExamStudentAssignment.assigned_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExamStudentAssignment)

    async def get_by_exam_and_student(
        self, exam_id: int, student_id: int
    ) -> ExamStudentAssignment | None:
        stmt = (
            select(ExamStudentAssignment)
            .where(ExamStudentAssignment.exam_id == exam_id)
            .where(ExamStudentAssignment.student_id == student_id)
            .where(ExamStudentAssignment.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_exam(self, exam_id: int) -> list[ExamStudentAssignment]:
        stmt = (
            select(ExamStudentAssignment)
            .where(ExamStudentAssignment.exam_id == exam_id)
            .where(ExamStudentAssignment.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class StudentAttemptRepository(BaseRepository[StudentAttempt]):
    """Repository for StudentAttempt tracking."""

    ALLOWED_SORT_FIELDS = {
        "started_at": StudentAttempt.started_at,
        "attempt_number": StudentAttempt.attempt_number,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudentAttempt)

    async def list_subject_ids_by_student(self, student_id: int) -> list[int]:
        """Distinct subject IDs the student has attempted (via their exams)."""
        stmt = (
            select(Exam.subject_id)
            .join(StudentAttempt, StudentAttempt.exam_id == Exam.id)
            .where(StudentAttempt.student_id == student_id)
            .where(StudentAttempt.is_deleted == False)  # noqa: E712
            .where(Exam.subject_id.isnot(None))
            .distinct()
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_latest_attempt(
        self, exam_id: int, student_id: int
    ) -> StudentAttempt | None:
        stmt = (
            select(StudentAttempt)
            .where(StudentAttempt.exam_id == exam_id)
            .where(StudentAttempt.student_id == student_id)
            .where(StudentAttempt.is_latest == True)  # noqa: E712
            .where(StudentAttempt.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_attempts_for_student(
        self, exam_id: int, student_id: int
    ) -> list[StudentAttempt]:
        stmt = (
            select(StudentAttempt)
            .where(StudentAttempt.exam_id == exam_id)
            .where(StudentAttempt.student_id == student_id)
            .where(StudentAttempt.is_deleted == False)  # noqa: E712
            .order_by(StudentAttempt.attempt_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_previous_attempts_not_latest(
        self, exam_id: int, student_id: int
    ) -> None:
        attempts = await self.list_attempts_for_student(exam_id, student_id)
        for att in attempts:
            att.is_latest = False
        await self.session.flush()
