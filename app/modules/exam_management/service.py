"""
Exam Management module — Service Layer (Phase 12).

Contains:
  1. `ExamService`: Exam state lifecycle, paper linkage, publishing, scheduling, and guest join.
  2. `AttemptService`: Student attempt execution (Regular vs Mock behavior per §6.5).
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser
from app.modules.blueprint.repository import ExamConfigRepository
from app.modules.exam_management.models import (
    Exam,
    ExamStatusHistory,
    ExamStudentAssignment,
    StudentAttempt,
)
from app.modules.exam_management.repository import (
    ExamRepository,
    ExamStatusHistoryRepository,
    ExamStudentAssignmentRepository,
    StudentAttemptRepository,
)
from app.modules.exam_management.schemas import (
    ExamConfigure,
    ExamCreate,
    ExamSchedule,
)
from app.modules.paper_generation.repository import PaperRepository
from app.modules.paper_generation.service import PaperGenerationService

logger = get_logger(__name__)


class ExamService:
    """Service orchestrating Exam lifecycle, assignments, and publishing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.exam_repo = ExamRepository(session)
        self.history_repo = ExamStatusHistoryRepository(session)
        self.assignment_repo = ExamStudentAssignmentRepository(session)
        self.ec_repo = ExamConfigRepository(session)
        self.paper_repo = PaperRepository(session)
        self.paper_service = PaperGenerationService(session)

    async def create_exam(
        self,
        data: ExamCreate,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Create a new exam in DRAFT state."""
        exam = await self.exam_repo.create(
            {
                "board_id": data.board_id,
                "school_id": data.school_id,
                "class_id": data.class_id,
                "subject_id": data.subject_id,
                "title": data.title,
                "exam_type": data.exam_type,
                "status": "DRAFT",
            }
        )
        # Log initial status history
        await self.history_repo.create(
            {
                "exam_id": exam.id,
                "from_status": "NONE",
                "to_status": "DRAFT",
                "changed_by": current_user.public_id if current_user else None,
                "changed_at": datetime.now(tz=timezone.utc),
            }
        )
        await self.session.commit()
        return self._exam_to_dict(exam)

    async def configure_exam(
        self,
        public_id: UUID,
        data: ExamConfigure,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Link an ExamConfiguration to the exam and transition DRAFT → CONFIGURED."""
        exam = await self.exam_repo.get_by(public_id=str(public_id))
        if exam is None:
            raise NotFoundError(f"Exam {public_id} not found")

        ec = await self.ec_repo.get_by_id(data.exam_configuration_id)
        if ec is None:
            raise NotFoundError(f"ExamConfiguration {data.exam_configuration_id} not found")

        exam.exam_configuration_id = ec.id
        await self.session.flush()

        actor_id = current_user.public_id if current_user else None
        updated_exam = await self.exam_repo.transition_status(
            exam.id, "CONFIGURED", actor_id=actor_id
        )
        await self.session.commit()
        return self._exam_to_dict(updated_exam)

    async def generate_papers_for_exam(
        self,
        public_id: UUID,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Trigger paper generation for exam → transition CONFIGURED → PAPER_GENERATED."""
        exam = await self.exam_repo.get_by(public_id=str(public_id))
        if exam is None:
            raise NotFoundError(f"Exam {public_id} not found")

        if exam.exam_configuration_id is None:
            raise BusinessRuleError("Exam must be configured before generating papers")

        # Generate shared paper (Phase 11)
        paper = await self.paper_service.generate_paper(
            exam_configuration_id=exam.exam_configuration_id,
            student_id=None,
            current_user=current_user,
        )

        actor_id = current_user.public_id if current_user else None
        updated_exam = await self.exam_repo.transition_status(
            exam.id, "PAPER_GENERATED", actor_id=actor_id
        )
        await self.session.commit()
        return self._exam_to_dict(updated_exam)

    async def approve_exam(
        self,
        public_id: UUID,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Approve exam papers → transition to APPROVED state."""
        exam = await self.exam_repo.get_by(public_id=str(public_id))
        if exam is None:
            raise NotFoundError(f"Exam {public_id} not found")

        # First transition to TEACHER_REVIEWING if in PAPER_GENERATED
        if exam.status == "PAPER_GENERATED":
            await self.exam_repo.transition_status(exam.id, "TEACHER_REVIEWING")

        actor_id = current_user.public_id if current_user else None
        updated_exam = await self.exam_repo.transition_status(
            exam.id, "APPROVED", actor_id=actor_id
        )
        await self.session.commit()
        return self._exam_to_dict(updated_exam)

    async def publish_exam(
        self,
        public_id: UUID,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Publish an approved exam → APPROVED → PUBLISHED.
        Generates join_code for guest access.
        """
        exam = await self.exam_repo.get_by(public_id=str(public_id))
        if exam is None:
            raise NotFoundError(f"Exam {public_id} not found")

        # Generate join code
        code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        exam.join_code = f"EXAM-{code}"
        await self.session.flush()

        actor_id = current_user.public_id if current_user else None
        updated_exam = await self.exam_repo.transition_status(
            exam.id, "PUBLISHED", actor_id=actor_id
        )
        await self.session.commit()
        return self._exam_to_dict(updated_exam)

    async def schedule_exam(
        self,
        public_id: UUID,
        schedule: ExamSchedule,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Schedule a published exam → PUBLISHED → SCHEDULED."""
        exam = await self.exam_repo.get_by(public_id=str(public_id))
        if exam is None:
            raise NotFoundError(f"Exam {public_id} not found")

        exam.scheduled_start_at = schedule.scheduled_start_at
        exam.scheduled_end_at = schedule.scheduled_end_at
        await self.session.flush()

        actor_id = current_user.public_id if current_user else None
        updated_exam = await self.exam_repo.transition_status(
            exam.id, "SCHEDULED", actor_id=actor_id
        )
        await self.session.commit()
        return self._exam_to_dict(updated_exam)

    async def join_guest(
        self,
        join_code: str,
        guest_name: str,
    ) -> dict[str, Any]:
        """
        Lazy-assign guest student to published exam via join code (Phase 12 §7).
        """
        exam = await self.exam_repo.get_by(join_code=join_code)
        if exam is None or exam.status not in ("PUBLISHED", "SCHEDULED", "ACTIVE"):
            raise NotFoundError("Invalid or inactive exam join code")

        from app.core.db.base_repository import BaseRepository
        from app.modules.identity.models import User
        from app.modules.student.models import StudentProfile

        # Create guest User first
        user_repo = BaseRepository(self.session, User)
        guest_email = f"guest-{join_code.lower()}-{secrets.token_hex(4)}@exam.guest"
        guest_user = await user_repo.create(
            {
                "email": guest_email,
                "user_type": "GUEST_STUDENT",
                "auth_source": "GUEST",
                "status": "ACTIVE",
                "school_id": exam.school_id,
            }
        )
        await self.session.flush()

        # Create guest student profile
        student_repo = BaseRepository(self.session, StudentProfile)
        guest_erp_id = f"GUEST-{join_code}-{secrets.token_hex(4)}"
        student = await student_repo.create(
            {
                "erp_student_id": guest_erp_id,
                "school_id": exam.school_id,
                "user_id": guest_user.id,
                "name": guest_name,
                "student_type": "GUEST",
            }
        )
        await self.session.flush()

        # Find available paper for this exam
        papers = await self.paper_repo.list_by_exam_config(exam.exam_configuration_id)
        if not papers:
            raise BusinessRuleError("No papers available for this exam")
        paper = papers[0]

        # Assign student
        assignment = await self.assignment_repo.create(
            {
                "exam_id": exam.id,
                "student_id": student.id,
                "paper_id": paper.id,
                "assigned_at": datetime.now(tz=timezone.utc),
                "status": "ASSIGNED",
            }
        )
        await self.session.commit()

        return {
            "exam_public_id": str(exam.public_id),
            "student_id": student.id,
            "paper_public_id": str(paper.public_id),
            "join_code": exam.join_code,
        }

    async def get_status_history(self, public_id: UUID) -> list[dict[str, Any]]:
        """Fetch exam status transition history."""
        exam = await self.exam_repo.get_by(public_id=str(public_id))
        if exam is None:
            raise NotFoundError(f"Exam {public_id} not found")

        history = await self.history_repo.list_by_exam(exam.id)
        return [
            {
                "public_id": str(h.public_id),
                "from_status": h.from_status,
                "to_status": h.to_status,
                "changed_by": h.changed_by,
                "changed_at": h.changed_at.isoformat(),
            }
            for h in history
        ]

    @staticmethod
    def _exam_to_dict(exam: Exam) -> dict[str, Any]:
        return {
            "id": exam.id,
            "public_id": str(exam.public_id),
            "exam_configuration_id": exam.exam_configuration_id,
            "board_id": exam.board_id,
            "school_id": exam.school_id,
            "class_id": exam.class_id,
            "subject_id": exam.subject_id,
            "title": exam.title,
            "status": exam.status,
            "exam_type": exam.exam_type,
            "scheduled_start_at": exam.scheduled_start_at.isoformat() if exam.scheduled_start_at else None,
            "scheduled_end_at": exam.scheduled_end_at.isoformat() if exam.scheduled_end_at else None,
            "actual_start_at": exam.actual_start_at.isoformat() if exam.actual_start_at else None,
            "actual_end_at": exam.actual_end_at.isoformat() if exam.actual_end_at else None,
            "published_at": exam.published_at.isoformat() if exam.published_at else None,
            "join_code": exam.join_code,
            "created_at": exam.created_at.isoformat(),
            "updated_at": exam.updated_at.isoformat(),
        }


class AttemptService:
    """Service managing Student Attempts (Regular vs Mock branching, §6.5)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.exam_repo = ExamRepository(session)
        self.assignment_repo = ExamStudentAssignmentRepository(session)
        self.attempt_repo = StudentAttemptRepository(session)
        self.paper_repo = PaperRepository(session)
        self.paper_service = PaperGenerationService(session)

    async def start_attempt(
        self,
        exam_public_id: UUID,
        student_id: int,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Start a student attempt for an exam.
        Regular: 1 attempt only. Returns 409 Conflict if attempt already exists/submitted.
        Mock: Multi-attempt. Generates a new paper per attempt, flips prior is_latest=False.
        """
        exam = await self.exam_repo.get_by(public_id=str(exam_public_id))
        if exam is None:
            raise NotFoundError(f"Exam {exam_public_id} not found")

        # Auto-activate exam if SCHEDULED/PUBLISHED
        if exam.status in ("PUBLISHED", "SCHEDULED"):
            await self.exam_repo.transition_status(exam.id, "ACTIVE")

        latest_attempt = await self.attempt_repo.get_latest_attempt(exam.id, student_id)

        if exam.exam_type == "REGULAR":
            if latest_attempt is not None:
                raise ConflictError(
                    f"Student {student_id} already has an attempt for Regular exam {exam_public_id}"
                )
            # Find assigned paper
            assignment = await self.assignment_repo.get_by_exam_and_student(exam.id, student_id)
            if assignment is None:
                # Assign default paper if not assigned
                papers = await self.paper_repo.list_by_exam_config(exam.exam_configuration_id)
                if not papers:
                    raise BusinessRuleError("No paper available for exam attempt")
                paper_id = papers[0].id
                assignment = await self.assignment_repo.create(
                    {
                        "exam_id": exam.id,
                        "student_id": student_id,
                        "paper_id": paper_id,
                        "assigned_at": datetime.now(tz=timezone.utc),
                        "status": "STARTED",
                    }
                )
            else:
                paper_id = assignment.paper_id
                assignment.status = "STARTED"

            attempt = await self.attempt_repo.create(
                {
                    "exam_id": exam.id,
                    "student_id": student_id,
                    "paper_id": paper_id,
                    "attempt_number": 1,
                    "status": "IN_PROGRESS",
                    "started_at": datetime.now(tz=timezone.utc),
                    "is_latest": True,
                }
            )

        else:  # MOCK EXAM
            attempt_num = 1
            if latest_attempt is not None:
                attempt_num = latest_attempt.attempt_number + 1
                await self.attempt_repo.mark_previous_attempts_not_latest(exam.id, student_id)

            # Generate new AI paper for this attempt (Phase 11 §8)
            paper_dict = await self.paper_service.generate_paper(
                exam_configuration_id=exam.exam_configuration_id,
                student_id=student_id,
                current_user=current_user,
            )
            paper = await self.paper_repo.get_by(public_id=paper_dict["public_id"])
            if paper is None:
                raise BusinessRuleError("Generated paper not found after generation")

            attempt = await self.attempt_repo.create(
                {
                    "exam_id": exam.id,
                    "student_id": student_id,
                    "paper_id": paper.id,
                    "attempt_number": attempt_num,
                    "status": "IN_PROGRESS",
                    "started_at": datetime.now(tz=timezone.utc),
                    "is_latest": True,
                }
            )

        await self.session.commit()
        return self._attempt_to_dict(attempt)

    async def submit_attempt(
        self,
        attempt_public_id: UUID,
        answers_summary_json: dict[str, Any] | None = None,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Submit an in-progress attempt → SUBMITTED."""
        attempt = await self.attempt_repo.get_by(public_id=str(attempt_public_id))
        if attempt is None:
            raise NotFoundError(f"Attempt {attempt_public_id} not found")

        if attempt.status != "IN_PROGRESS":
            raise ConflictError(f"Attempt is already in status '{attempt.status}'")

        now = datetime.now(tz=timezone.utc)
        attempt.status = "SUBMITTED"
        attempt.submitted_at = now

        # Update assignment status if exists
        assignment = await self.assignment_repo.get_by_exam_and_student(
            attempt.exam_id, attempt.student_id
        )
        if assignment:
            assignment.status = "SUBMITTED"

        await self.session.commit()

        # Emit ExamSubmitted domain event (for Phase 13 Evaluation intake)
        from app.modules.exam_management.events import ExamSubmitted, publish_exam_submitted
        await publish_exam_submitted(
            ExamSubmitted(
                attempt_public_id=str(attempt.public_id),
                exam_id=attempt.exam_id,
                student_id=attempt.student_id,
                paper_id=attempt.paper_id,
                submitted_at=now.isoformat(),
            )
        )

        return self._attempt_to_dict(attempt)

    @staticmethod
    def _attempt_to_dict(att: StudentAttempt) -> dict[str, Any]:
        return {
            "id": att.id,
            "public_id": str(att.public_id),
            "exam_id": att.exam_id,
            "student_id": att.student_id,
            "paper_id": att.paper_id,
            "attempt_number": att.attempt_number,
            "status": att.status,
            "started_at": att.started_at.isoformat() if att.started_at else None,
            "submitted_at": att.submitted_at.isoformat() if att.submitted_at else None,
            "is_latest": att.is_latest,
            "created_at": att.created_at.isoformat() if att.created_at else None,
        }
