"""
Evaluation Engine module — Service Layer (Phase 13).

Contains:
  1. `OMRService`: Scanned image processing, bubble detection, answer matching, and auto-mapping topic_id/chapter_id.
  2. `SubjectiveEvaluationService`: Teacher subjective marks entry with auto topic mapping.
  3. `EvaluationService`: Hybrid merge, lock validation, re-evaluation approval & version snapshotting.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser
from app.modules.evaluation.domain.omr.bubble_detection import detect_bubbles_from_matrix
from app.modules.evaluation.models import (
    Evaluation,
    EvaluationDetail,
    EvaluationVersion,
    OMRResult,
    OMRUpload,
    ReEvaluationRequest,
    SubjectiveEvaluation,
)
from app.modules.evaluation.repository import (
    EvaluationDetailRepository,
    EvaluationRepository,
    EvaluationVersionRepository,
    OMRResultRepository,
    OMRUploadRepository,
    ReEvaluationRequestRepository,
    SubjectiveEvaluationRepository,
)
from app.modules.exam_management.repository import StudentAttemptRepository
from app.modules.paper_generation.repository import PaperQuestionRepository, PaperSectionRepository
from app.modules.question_bank.repository import (
    FillBlankQuestionRepository,
    ObjectiveQuestionRepository,
    SubjectiveQuestionRepository,
)

logger = get_logger(__name__)


class EvaluationService:
    """Service orchestrating Evaluation state lifecycle, lock, hybrid merge, and re-evaluation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.eval_repo = EvaluationRepository(session)
        self.detail_repo = EvaluationDetailRepository(session)
        self.version_repo = EvaluationVersionRepository(session)
        self.re_eval_repo = ReEvaluationRequestRepository(session)
        self.attempt_repo = StudentAttemptRepository(session)
        self.omr_upload_repo = OMRUploadRepository(session)

    async def get_or_create_evaluation(self, attempt_id: int) -> Evaluation:
        """Fetch or initialize Evaluation aggregate root for attempt_id."""
        eval_obj = await self.eval_repo.get_by_attempt(attempt_id)
        if eval_obj is None:
            attempt = await self.attempt_repo.get_or_raise(attempt_id)
            eval_obj = await self.eval_repo.create(
                {
                    "attempt_id": attempt.id,
                    "status": "PENDING",
                    "current_version_no": 1,
                }
            )
            await self.session.flush()
        return eval_obj

    async def complete_evaluation(
        self,
        public_id: UUID,
        pass_threshold_pct: float = 40.0,
    ) -> dict[str, Any]:
        """
        Merge objective & subjective marks, compute total_marks, percentage, result_status (PASS/FAIL).
        Transitions status → COMPLETED.
        """
        eval_obj = await self.eval_repo.get_by(public_id=str(public_id))
        if eval_obj is None:
            raise NotFoundError(f"Evaluation {public_id} not found")

        details = await self.detail_repo.list_by_evaluation(eval_obj.id)
        if not details:
            raise BusinessRuleError("Cannot complete evaluation with no evaluated details")

        obj_marks = sum(float(d.marks_obtained) for d in details if d.evaluated_by == "OMR")
        subj_marks = sum(float(d.marks_obtained) for d in details if d.evaluated_by == "TEACHER")
        total = obj_marks + subj_marks
        max_possible = sum(float(d.max_marks) for d in details)

        pct = round((total / max_possible * 100.0), 2) if max_possible > 0 else 0.0
        res_status = "PASS" if pct >= pass_threshold_pct else "FAIL"

        eval_obj.objective_marks = round(obj_marks, 2)
        eval_obj.subjective_marks = round(subj_marks, 2)
        eval_obj.total_marks = round(total, 2)
        eval_obj.percentage = pct
        eval_obj.result_status = res_status
        await self.session.flush()

        # Transition status
        await self.eval_repo.transition_status(eval_obj.id, "COMPLETED")
        await self.session.commit()

        logger.info(
            "Evaluation completed",
            public_id=str(eval_obj.public_id),
            total_marks=eval_obj.total_marks,
            result_status=res_status,
        )
        return self._eval_to_dict(eval_obj)

    async def lock_evaluation(
        self,
        public_id: UUID,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Lock evaluation → COMPLETED → LOCKED.
        Blocks lock if any unresolved OMR NEEDS_MANUAL_REVIEW flag exists.
        Publishes EvaluationCompleted event.
        """
        eval_obj = await self.eval_repo.get_by(public_id=str(public_id))
        if eval_obj is None:
            raise NotFoundError(f"Evaluation {public_id} not found")

        # Check OMR manual review status (§13 validation rule)
        omr_upload = await self.omr_upload_repo.get_by_attempt(eval_obj.attempt_id)
        if omr_upload and omr_upload.status == "NEEDS_MANUAL_REVIEW":
            raise BusinessRuleError(
                "Cannot lock evaluation with unresolved OMR NEEDS_MANUAL_REVIEW flags"
            )

        actor_id = current_user.public_id if current_user else None
        eval_obj.locked_by = actor_id
        eval_obj.locked_at = datetime.now(tz=timezone.utc)
        await self.session.flush()

        await self.eval_repo.transition_status(eval_obj.id, "LOCKED")
        await self.session.commit()

        # Emit EvaluationCompleted domain event for Phase 14 Mastery Engine
        from app.modules.evaluation.events import EvaluationCompleted, publish_evaluation_completed
        await publish_evaluation_completed(
            EvaluationCompleted(
                evaluation_public_id=str(eval_obj.public_id),
                attempt_id=eval_obj.attempt_id,
                total_marks=float(eval_obj.total_marks or 0.0),
                percentage=float(eval_obj.percentage or 0.0),
                result_status=eval_obj.result_status or "FAIL",
            )
        )

        return self._eval_to_dict(eval_obj)

    async def request_re_evaluation(
        self,
        public_id: UUID,
        reason: str,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Create a re-evaluation request for a locked evaluation."""
        eval_obj = await self.eval_repo.get_by(public_id=str(public_id))
        if eval_obj is None:
            raise NotFoundError(f"Evaluation {public_id} not found")

        req = await self.re_eval_repo.create(
            {
                "evaluation_id": eval_obj.id,
                "requested_by": current_user.public_id if current_user else None,
                "reason": reason,
                "status": "PENDING",
            }
        )
        await self.session.commit()
        return {
            "public_id": str(req.public_id),
            "evaluation_id": req.evaluation_id,
            "status": req.status,
            "reason": req.reason,
        }

    async def approve_re_evaluation(
        self,
        request_public_id: UUID,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Approve re-evaluation:
        1. Snapshot current evaluation state to evaluation_versions v(N).
        2. Unlock evaluation back to STARTED.
        3. Increment version number.
        """
        req = await self.re_eval_repo.get_by(public_id=str(request_public_id))
        if req is None:
            raise NotFoundError(f"ReEvaluationRequest {request_public_id} not found")

        eval_obj = await self.eval_repo.get_or_raise(req.evaluation_id)
        details = await self.detail_repo.list_by_evaluation(eval_obj.id)

        # Snapshot current version
        snapshot_json = {
            "evaluation": self._eval_to_dict(eval_obj),
            "details": [
                {
                    "question_id": d.question_id,
                    "marks_obtained": float(d.marks_obtained),
                    "max_marks": float(d.max_marks),
                }
                for d in details
            ],
        }

        await self.version_repo.create(
            {
                "evaluation_id": eval_obj.id,
                "version_no": eval_obj.current_version_no,
                "snapshot_json": snapshot_json,
                "reason": req.reason,
                "requested_by": req.requested_by,
            }
        )

        # Increment version and unlock to STARTED
        eval_obj.current_version_no += 1
        eval_obj.locked_by = None
        eval_obj.locked_at = None
        await self.eval_repo.transition_status(eval_obj.id, "STARTED")

        req.status = "APPROVED"
        req.approved_by = current_user.public_id if current_user else None
        await self.session.commit()

        return self._eval_to_dict(eval_obj)

    @staticmethod
    def _eval_to_dict(ev: Evaluation) -> dict[str, Any]:
        return {
            "public_id": str(ev.public_id),
            "attempt_id": ev.attempt_id,
            "status": ev.status,
            "objective_marks": float(ev.objective_marks) if ev.objective_marks is not None else None,
            "subjective_marks": float(ev.subjective_marks) if ev.subjective_marks is not None else None,
            "total_marks": float(ev.total_marks) if ev.total_marks is not None else None,
            "percentage": float(ev.percentage) if ev.percentage is not None else None,
            "result_status": ev.result_status,
            "locked_at": ev.locked_at.isoformat() if ev.locked_at else None,
            "current_version_no": ev.current_version_no,
            "created_at": ev.created_at.isoformat(),
            "updated_at": ev.updated_at.isoformat(),
        }


class OMRService:
    """Service processing scanned OMR sheets and matching objective answers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.eval_service = EvaluationService(session)
        self.eval_repo = EvaluationRepository(session)
        self.detail_repo = EvaluationDetailRepository(session)
        self.upload_repo = OMRUploadRepository(session)
        self.result_repo = OMRResultRepository(session)
        self.attempt_repo = StudentAttemptRepository(session)
        self.pq_repo = PaperQuestionRepository(session)
        self.ps_repo = PaperSectionRepository(session)
        self.obj_q_repo = ObjectiveQuestionRepository(session)

    async def process_omr_upload(
        self,
        attempt_id: int,
        raw_bubble_matrix: dict[str, dict[str, float]],
        upload_source: str = "WEB_UPLOAD",
    ) -> dict[str, Any]:
        """
        Process OMR upload:
        1. Run bubble detection logic (Phase 13 §7).
        2. Match detected answers against paper's correct options.
        3. AUTO-RESOLVE chapter_id & topic_id from question metadata (Phase 10).
        4. Populate evaluation_details with question-wise marks.
        """
        attempt = await self.attempt_repo.get_or_raise(attempt_id)
        eval_obj = await self.eval_service.get_or_create_evaluation(attempt_id)

        # Perform bubble detection
        det_result = detect_bubbles_from_matrix(raw_bubble_matrix)
        status = "NEEDS_MANUAL_REVIEW" if det_result.low_confidence_questions else "DETECTED"

        upload = await self.upload_repo.create(
            {
                "attempt_id": attempt.id,
                "upload_source": upload_source,
                "status": status,
            }
        )
        await self.session.flush()

        res = await self.result_repo.create(
            {
                "omr_upload_id": upload.id,
                "detected_grid_json": det_result.detected_grid,
                "detected_answers_json": det_result.detected_answers,
                "confidence_score": det_result.confidence_score,
                "low_confidence_questions_json": det_result.low_confidence_questions,
            }
        )
        await self.session.flush()

        # Match objective questions and auto-map topics
        sections = await self.ps_repo.list_by_paper(attempt.paper_id)
        seq = 1
        now = datetime.now(tz=timezone.utc)

        for sec in sections:
            if sec.question_type != "OBJECTIVE":
                continue
            questions = await self.pq_repo.list_by_section(sec.id)
            for pq in questions:
                q_num_str = str(seq)
                detected = det_result.detected_answers.get(q_num_str)

                # Fetch question metadata for topic mapping
                obj_q = await self.obj_q_repo.get_by_id(pq.question_id)
                chapter_id = obj_q.primary_chapter_id if obj_q else None
                topic_id = obj_q.primary_topic_id if obj_q else None
                correct_opt = obj_q.correct_option if obj_q else None

                is_correct = (detected == correct_opt) if (detected and correct_opt) else False
                marks = float(pq.marks) if is_correct else 0.0

                # Check if detail row already exists
                existing = await self.detail_repo.get_detail_for_question(
                    eval_obj.id, pq.question_id, question_type="OBJECTIVE"
                )
                if existing:
                    existing.marks_obtained = marks
                    existing.is_correct = is_correct
                    existing.evaluated_by = "OMR"
                    existing.evaluated_at = now
                else:
                    await self.detail_repo.create(
                        {
                            "evaluation_id": eval_obj.id,
                            "paper_question_id": pq.id,
                            "question_type": "OBJECTIVE",
                            "question_id": pq.question_id,
                            "chapter_id": chapter_id,
                            "topic_id": topic_id,
                            "marks_obtained": marks,
                            "max_marks": float(pq.marks),
                            "is_correct": is_correct,
                            "evaluated_by": "OMR",
                            "evaluated_at": now,
                        }
                    )
                seq += 1

        # Transition evaluation state
        await self.eval_repo.transition_status(eval_obj.id, "OBJECTIVE_COMPLETED")
        await self.session.commit()

        return {
            "upload_public_id": str(upload.public_id),
            "status": upload.status,
            "confidence_score": det_result.confidence_score,
            "low_confidence_count": len(det_result.low_confidence_questions),
        }


class SubjectiveEvaluationService:
    """Service handling teacher subjective marking with automatic topic mapping."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.eval_service = EvaluationService(session)
        self.eval_repo = EvaluationRepository(session)
        self.detail_repo = EvaluationDetailRepository(session)
        self.subj_q_repo = SubjectiveQuestionRepository(session)
        self.fill_q_repo = FillBlankQuestionRepository(session)

    async def enter_subjective_marks(
        self,
        evaluation_public_id: UUID,
        question_id: int,
        question_type: str,
        marks_obtained: float,
        max_marks: float,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Record subjective marks for a question.
        AUTO-RESOLVES chapter_id & topic_id from question ORM metadata (Phase 13 §6.2).
        Teacher NEVER enters chapter/topic manually.
        """
        eval_obj = await self.eval_repo.get_by(public_id=str(evaluation_public_id))
        if eval_obj is None:
            raise NotFoundError(f"Evaluation {evaluation_public_id} not found")

        if eval_obj.status == "LOCKED":
            raise BusinessRuleError("Cannot edit details of a LOCKED evaluation")

        if marks_obtained > max_marks:
            raise ValidationError(f"marks_obtained ({marks_obtained}) cannot exceed max_marks ({max_marks})")

        # Resolve question chapter_id & topic_id automatically
        chapter_id, topic_id = None, None
        if question_type == "SUBJECTIVE":
            sq = await self.subj_q_repo.get_by_id(question_id)
            if sq:
                chapter_id, topic_id = sq.primary_chapter_id, sq.primary_topic_id
        elif question_type == "FILL_BLANK":
            fq = await self.fill_q_repo.get_by_id(question_id)
            if fq:
                chapter_id, topic_id = fq.primary_chapter_id, fq.primary_topic_id

        now = datetime.now(tz=timezone.utc)
        existing = await self.detail_repo.get_detail_for_question(
            eval_obj.id, question_id, question_type=question_type
        )
        if existing:
            existing.marks_obtained = marks_obtained
            existing.max_marks = max_marks
            existing.evaluated_by = "TEACHER"
            existing.evaluated_at = now
            detail = existing
        else:
            detail = await self.detail_repo.create(
                {
                    "evaluation_id": eval_obj.id,
                    "question_type": question_type,
                    "question_id": question_id,
                    "chapter_id": chapter_id,
                    "topic_id": topic_id,
                    "marks_obtained": marks_obtained,
                    "max_marks": max_marks,
                    "is_correct": marks_obtained == max_marks,
                    "evaluated_by": "TEACHER",
                    "evaluated_at": now,
                }
            )

        if eval_obj.status in ("PENDING", "STARTED", "OBJECTIVE_COMPLETED"):
            await self.eval_repo.transition_status(eval_obj.id, "SUBJECTIVE_PENDING")

        await self.session.commit()
        return {
            "public_id": str(detail.public_id),
            "evaluation_id": detail.evaluation_id,
            "question_id": detail.question_id,
            "chapter_id": detail.chapter_id,
            "topic_id": detail.topic_id,
            "marks_obtained": float(detail.marks_obtained),
            "max_marks": float(detail.max_marks),
        }
