"""
Mastery Engine module — Service layer (Phase 14 §5).

Contains:
  1. `MasteryService`: Consumes EvaluationCompleted event, reads EvaluationDetail rows,
     applies EMA mastery update per topic, aggregates chapter/subject scores,
     and appends MasteryHistory audit records.
  2. `LearningProfileService`: Queries and exposes student learning profile
     (weak topics, strong topics, subject-level overview).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.modules.evaluation.models import EvaluationDetail
from app.modules.evaluation.repository import (
    EvaluationDetailRepository,
    EvaluationRepository,
)
from app.modules.learning_profile.domain.mastery_formula import (
    EMAMasteryFormula,
    MasteryFormula,
    aggregate_mastery,
    compute_question_score,
)
from app.modules.learning_profile.repository import (
    MasteryHistoryRepository,
    StudentChapterMasteryRepository,
    StudentSubjectMasteryRepository,
    StudentTopicMasteryRepository,
)

logger = get_logger(__name__)

# Classification thresholds (Phase 14 §3.2)
WEAK_THRESHOLD = 0.5    # mastery < 0.5  → weak topic (needs practice)
STRONG_THRESHOLD = 0.8  # mastery >= 0.8 → strong topic (confident)


class MasteryService:
    """
    Consumes locked Evaluation and updates the student mastery profile.

    Called from:
      - `EvaluationService.lock_evaluation()` (same session, synchronous in Phase 14).
      - Phase 17: replaced with async event bus consumer.

    Algorithm (per EvaluationDetail row):
      1. Resolve student_id from attempt.
      2. For each EvaluationDetail with a valid topic_id:
         a. Compute question_score = marks_obtained / max_marks.
         b. Get or create StudentTopicMastery row.
         c. Apply EMA formula → new_mastery.
         d. Update attempt_count, correct_count.
         e. Append MasteryHistory audit row.
      3. Recompute chapter mastery = avg(topic masteries in chapter).
      4. Recompute subject mastery = avg(chapter masteries in subject).
    """

    def __init__(
        self,
        session: AsyncSession,
        formula: MasteryFormula | None = None,
    ) -> None:
        self.session = session
        self.formula: MasteryFormula = formula or EMAMasteryFormula()
        self.topic_repo = StudentTopicMasteryRepository(session)
        self.chapter_repo = StudentChapterMasteryRepository(session)
        self.subject_repo = StudentSubjectMasteryRepository(session)
        self.history_repo = MasteryHistoryRepository(session)
        self.eval_repo = EvaluationRepository(session)
        self.detail_repo = EvaluationDetailRepository(session)

    async def process_evaluation(
        self,
        evaluation_public_id: UUID | str,
    ) -> dict[str, Any]:
        """
        Entry point: given a locked evaluation's public_id, update mastery for all
        EvaluationDetail rows that have a valid topic_id.

        Returns summary dict: {student_id, topics_updated, chapters_updated, subjects_updated}.
        """
        # Resolve evaluation → attempt → student
        eval_obj = await self.eval_repo.get_by(public_id=str(evaluation_public_id))
        if eval_obj is None:
            raise NotFoundError(f"Evaluation {evaluation_public_id} not found")

        # Fetch student from attempt
        from app.modules.exam_management.repository import StudentAttemptRepository
        attempt_repo = StudentAttemptRepository(self.session)
        attempt = await attempt_repo.get_or_raise(eval_obj.attempt_id)
        student_id = attempt.student_id

        # Fetch all evaluation details
        details: list[EvaluationDetail] = await self.detail_repo.list_by_evaluation(
            eval_obj.id
        )

        # Track which chapters/subjects need re-aggregation
        updated_chapters: set[int] = set()
        updated_subjects: set[int] = set()
        topics_updated = 0
        now = datetime.now(tz=timezone.utc)

        from app.modules.academic.repository import ChapterRepository
        chap_repo = ChapterRepository(self.session)

        for detail in details:
            # Skip rows without topic/chapter mapping
            if detail.topic_id is None or detail.chapter_id is None:
                logger.warning(
                    "mastery.skipped_detail_missing_topic",
                    detail_id=detail.id,
                    evaluation_id=eval_obj.id,
                )
                continue

            chapter_obj = await chap_repo.get_by_id(detail.chapter_id)
            if chapter_obj is None:
                continue
            subject_id = chapter_obj.subject_id

            q_score = compute_question_score(
                float(detail.marks_obtained), float(detail.max_marks)
            )

            # Get or create mastery row
            mastery_row = await self.topic_repo.get_or_create(
                student_id=student_id,
                topic_id=detail.topic_id,
                chapter_id=detail.chapter_id,
                subject_id=subject_id,
            )

            current_mastery = float(mastery_row.mastery_score)
            attempt_count = mastery_row.attempt_count

            # Apply formula
            new_mastery, alpha = self.formula.compute(
                current_mastery=current_mastery,
                question_score=q_score,
                attempt_count=attempt_count,
            )

            # Append audit history BEFORE updating the mastery row
            await self.history_repo.create(
                {
                    "student_id": student_id,
                    "topic_id": detail.topic_id,
                    "chapter_id": detail.chapter_id,
                    "subject_id": subject_id,
                    "evaluation_id": eval_obj.id,
                    "question_score": q_score,
                    "mastery_before": current_mastery,
                    "mastery_after": new_mastery,
                    "alpha_used": alpha,
                    "evaluated_at": now,
                }
            )

            # Update mastery row
            mastery_row.mastery_score = new_mastery
            mastery_row.attempt_count = attempt_count + 1
            if q_score >= 1.0:
                mastery_row.correct_count = mastery_row.correct_count + 1
            mastery_row.last_evaluated_at = now

            updated_chapters.add(detail.chapter_id)
            updated_subjects.add(subject_id)
            topics_updated += 1

        await self.session.flush()

        # Recompute chapter-level mastery
        for chapter_id in updated_chapters:
            await self._recompute_chapter_mastery(student_id, chapter_id)

        # Recompute subject-level mastery
        for subject_id in updated_subjects:
            await self._recompute_subject_mastery(student_id, subject_id)

        await self.session.commit()

        logger.info(
            "mastery.evaluation_processed",
            evaluation_public_id=str(evaluation_public_id),
            student_id=student_id,
            topics_updated=topics_updated,
            chapters_updated=len(updated_chapters),
            subjects_updated=len(updated_subjects),
        )

        return {
            "student_id": student_id,
            "topics_updated": topics_updated,
            "chapters_updated": len(updated_chapters),
            "subjects_updated": len(updated_subjects),
        }

    async def _recompute_chapter_mastery(
        self, student_id: int, chapter_id: int
    ) -> None:
        """
        Recompute chapter mastery = average of all topic masteries in the chapter.
        Creates the chapter row if absent.
        """
        topic_rows = await self.topic_repo.list_by_student_chapter(student_id, chapter_id)
        if not topic_rows:
            return

        scores = [float(r.mastery_score) for r in topic_rows]
        avg_score = aggregate_mastery(scores)
        subject_id = topic_rows[0].subject_id
        now = datetime.now(tz=timezone.utc)

        chapter_row = await self.chapter_repo.get_or_create(
            student_id=student_id,
            chapter_id=chapter_id,
            subject_id=subject_id,
        )
        chapter_row.mastery_score = avg_score
        chapter_row.topic_count = len(scores)
        chapter_row.last_updated_at = now
        await self.session.flush()

    async def _recompute_subject_mastery(
        self, student_id: int, subject_id: int
    ) -> None:
        """
        Recompute subject mastery = average of all chapter masteries in the subject.
        Creates the subject row if absent.
        """
        chapter_rows = await self.chapter_repo.list_by_student(student_id)
        subject_chapters = [r for r in chapter_rows if r.subject_id == subject_id]
        if not subject_chapters:
            return

        scores = [float(r.mastery_score) for r in subject_chapters]
        avg_score = aggregate_mastery(scores)
        now = datetime.now(tz=timezone.utc)

        subject_row = await self.subject_repo.get_or_create(
            student_id=student_id,
            subject_id=subject_id,
        )
        subject_row.mastery_score = avg_score
        subject_row.chapter_count = len(scores)
        subject_row.last_updated_at = now
        await self.session.flush()


class LearningProfileService:
    """
    Exposes student learning profile for the recommendation and analytics engines.

    Provides:
      - Full profile: all topic/chapter/subject masteries.
      - Weak topics: mastery < WEAK_THRESHOLD (for Phase 15 Recommendation).
      - Strong topics: mastery >= STRONG_THRESHOLD.
      - Subject overview: top-level percentage for dashboard.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.topic_repo = StudentTopicMasteryRepository(session)
        self.chapter_repo = StudentChapterMasteryRepository(session)
        self.subject_repo = StudentSubjectMasteryRepository(session)
        self.history_repo = MasteryHistoryRepository(session)

    async def get_learning_profile(
        self,
        student_id: int,
        subject_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Return full learning profile for a student.

        If `subject_id` is given, scope topic/chapter results to that subject.
        """
        if subject_id is not None:
            topic_rows = await self.topic_repo.list_by_student_subject(
                student_id, subject_id
            )
        else:
            topic_rows = await self.topic_repo.list_by_student(student_id)

        chapter_rows = await self.chapter_repo.list_by_student(student_id)
        subject_rows = await self.subject_repo.list_by_student(student_id)

        if subject_id is not None:
            chapter_rows = [r for r in chapter_rows if r.subject_id == subject_id]
            subject_rows = [r for r in subject_rows if r.subject_id == subject_id]

        weak_topic_ids = [
            r.topic_id for r in topic_rows if float(r.mastery_score) < WEAK_THRESHOLD
        ]
        strong_topic_ids = [
            r.topic_id for r in topic_rows if float(r.mastery_score) >= STRONG_THRESHOLD
        ]

        return {
            "student_id": student_id,
            "subject_masteries": [self._subject_to_dict(r) for r in subject_rows],
            "chapter_masteries": [self._chapter_to_dict(r) for r in chapter_rows],
            "topic_masteries": [self._topic_to_dict(r) for r in topic_rows],
            "weak_topic_ids": weak_topic_ids,
            "strong_topic_ids": strong_topic_ids,
        }

    async def get_weak_topics(
        self,
        student_id: int,
        subject_id: int | None = None,
    ) -> list[int]:
        """Return topic IDs where student mastery is below WEAK_THRESHOLD."""
        profile = await self.get_learning_profile(student_id, subject_id=subject_id)
        return profile["weak_topic_ids"]

    async def get_topic_mastery_history(
        self,
        student_id: int,
        topic_id: int,
    ) -> list[dict[str, Any]]:
        """Return chronological mastery history for a student × topic pair."""
        rows = await self.history_repo.list_by_student_topic(student_id, topic_id)
        return [
            {
                "topic_id": r.topic_id,
                "evaluation_id": r.evaluation_id,
                "question_score": float(r.question_score),
                "mastery_before": float(r.mastery_before),
                "mastery_after": float(r.mastery_after),
                "alpha_used": float(r.alpha_used),
                "evaluated_at": r.evaluated_at.isoformat(),
            }
            for r in rows
        ]

    @staticmethod
    def _topic_to_dict(r: Any) -> dict[str, Any]:
        return {
            "topic_id": r.topic_id,
            "chapter_id": r.chapter_id,
            "subject_id": r.subject_id,
            "mastery_score": float(r.mastery_score),
            "attempt_count": r.attempt_count,
            "correct_count": r.correct_count,
            "last_evaluated_at": r.last_evaluated_at.isoformat() if r.last_evaluated_at else None,
        }

    @staticmethod
    def _chapter_to_dict(r: Any) -> dict[str, Any]:
        return {
            "chapter_id": r.chapter_id,
            "subject_id": r.subject_id,
            "mastery_score": float(r.mastery_score),
            "topic_count": r.topic_count,
            "last_updated_at": r.last_updated_at.isoformat() if r.last_updated_at else None,
        }

    @staticmethod
    def _subject_to_dict(r: Any) -> dict[str, Any]:
        return {
            "subject_id": r.subject_id,
            "mastery_score": float(r.mastery_score),
            "chapter_count": r.chapter_count,
            "last_updated_at": r.last_updated_at.isoformat() if r.last_updated_at else None,
        }
