"""
Evaluation Engine module — Repository layer (Phase 13).

Provides specialized repositories inheriting `BaseRepository[ModelT]`:
  - `EvaluationRepository`
  - `EvaluationDetailRepository`
  - `OMRUploadRepository`
  - `OMRResultRepository`
  - `SubjectiveEvaluationRepository`
  - `EvaluationVersionRepository`
  - `ReEvaluationRequestRepository`
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.evaluation.domain.state_machine import validate_evaluation_transition
from app.modules.evaluation.models import (
    Evaluation,
    EvaluationDetail,
    EvaluationVersion,
    OMRResult,
    OMRUpload,
    ReEvaluationRequest,
    SubjectiveEvaluation,
)


class EvaluationRepository(BaseRepository[Evaluation]):
    """Repository for Evaluation aggregate root."""

    ALLOWED_SORT_FIELDS = {
        "created_at": Evaluation.created_at,
        "total_marks": Evaluation.total_marks,
        "percentage": Evaluation.percentage,
        "status": Evaluation.status,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Evaluation)

    async def get_by_attempt(self, attempt_id: int) -> Evaluation | None:
        stmt = (
            select(Evaluation)
            .where(Evaluation.attempt_id == attempt_id)
            .where(Evaluation.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def transition_status(self, evaluation_id: int, target_status: str) -> Evaluation:
        """
        The ONLY authoritative method to transition an Evaluation's status.
        Validates transition via state_machine.py.
        """
        eval_obj = await self.get_or_raise(evaluation_id)
        validate_evaluation_transition(eval_obj.status, target_status)
        eval_obj.status = target_status
        await self.session.flush()
        return eval_obj


class EvaluationDetailRepository(BaseRepository[EvaluationDetail]):
    """Repository for question-wise marks details."""

    ALLOWED_SORT_FIELDS = {"evaluated_at": EvaluationDetail.evaluated_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EvaluationDetail)

    async def list_by_evaluation(self, evaluation_id: int) -> list[EvaluationDetail]:
        stmt = (
            select(EvaluationDetail)
            .where(EvaluationDetail.evaluation_id == evaluation_id)
            .where(EvaluationDetail.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_detail_for_question(
        self, evaluation_id: int, question_id: int, question_type: str | None = None
    ) -> EvaluationDetail | None:
        stmt = (
            select(EvaluationDetail)
            .where(EvaluationDetail.evaluation_id == evaluation_id)
            .where(EvaluationDetail.question_id == question_id)
            .where(EvaluationDetail.is_deleted == False)  # noqa: E712
        )
        if question_type is not None:
            stmt = stmt.where(EvaluationDetail.question_type == question_type)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class OMRUploadRepository(BaseRepository[OMRUpload]):
    """Repository for OMR sheet upload rows."""

    ALLOWED_SORT_FIELDS = {"created_at": OMRUpload.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OMRUpload)

    async def get_by_attempt(self, attempt_id: int) -> OMRUpload | None:
        stmt = (
            select(OMRUpload)
            .where(OMRUpload.attempt_id == attempt_id)
            .where(OMRUpload.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class OMRResultRepository(BaseRepository[OMRResult]):
    """Repository for OMR detection results."""

    ALLOWED_SORT_FIELDS = {"confidence_score": OMRResult.confidence_score}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OMRResult)

    async def get_by_upload(self, omr_upload_id: int) -> OMRResult | None:
        stmt = (
            select(OMRResult)
            .where(OMRResult.omr_upload_id == omr_upload_id)
            .where(OMRResult.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class SubjectiveEvaluationRepository(BaseRepository[SubjectiveEvaluation]):
    """Repository for Subjective evaluation submissions."""

    ALLOWED_SORT_FIELDS = {"evaluated_at": SubjectiveEvaluation.evaluated_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SubjectiveEvaluation)


class EvaluationVersionRepository(BaseRepository[EvaluationVersion]):
    """Repository for re-evaluation snapshot versions."""

    ALLOWED_SORT_FIELDS = {"version_no": EvaluationVersion.version_no}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EvaluationVersion)

    async def list_by_evaluation(self, evaluation_id: int) -> list[EvaluationVersion]:
        stmt = (
            select(EvaluationVersion)
            .where(EvaluationVersion.evaluation_id == evaluation_id)
            .order_by(EvaluationVersion.version_no.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ReEvaluationRequestRepository(BaseRepository[ReEvaluationRequest]):
    """Repository for re-evaluation requests."""

    ALLOWED_SORT_FIELDS = {"created_at": ReEvaluationRequest.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ReEvaluationRequest)
