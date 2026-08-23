"""
Evaluation Engine module — FastAPI router (Phase 13).

All endpoints delegate to OMRService, SubjectiveEvaluationService, and EvaluationService.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.evaluation.schemas import (
    EvaluationCompleteRequest,
    EvaluationResponse,
    OMRManualReviewRequest,
    OMRUploadRequest,
    ReEvaluationRequestCreate,
    SubjectiveMarksEntry,
)
from app.modules.evaluation.service import (
    EvaluationService,
    OMRService,
    SubjectiveEvaluationService,
)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "evaluation"}


# ------------------------------------------------------------------------- OMR --

@router.post("/omr/upload", status_code=201)
async def process_omr_upload(
    payload: OMRUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Process scanned OMR sheet and calculate objective question marks."""
    service = OMRService(db)
    return await service.process_omr_upload(
        attempt_id=payload.attempt_id,
        raw_bubble_matrix=payload.raw_bubble_matrix or {},
        upload_source=payload.upload_source,
    )


# ------------------------------------------------------------------ Subjective --

@router.patch("/evaluations/{public_id}/subjective-marks")
async def enter_subjective_marks(
    public_id: UUID,
    payload: SubjectiveMarksEntry,
    question_type: str = "SUBJECTIVE",
    max_marks: float = 5.0,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Enter question-wise subjective marks with auto topic mapping."""
    service = SubjectiveEvaluationService(db)
    return await service.enter_subjective_marks(
        evaluation_public_id=public_id,
        question_id=payload.question_id,
        question_type=question_type,
        marks_obtained=payload.marks_obtained,
        max_marks=max_marks,
        current_user=current_user,
    )


# ------------------------------------------------------------------ Evaluation --

@router.post("/evaluations/{public_id}/complete", response_model=EvaluationResponse)
async def complete_evaluation(
    public_id: UUID,
    payload: EvaluationCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Merge objective & subjective marks, compute totals and pass/fail."""
    service = EvaluationService(db)
    return await service.complete_evaluation(
        public_id, pass_threshold_pct=payload.pass_threshold_pct
    )


@router.post("/evaluations/{public_id}/lock", response_model=EvaluationResponse)
async def lock_evaluation(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Lock evaluation (COMPLETED → LOCKED) and publish EvaluationCompleted event."""
    service = EvaluationService(db)
    return await service.lock_evaluation(public_id, current_user=current_user)


@router.post("/evaluations/{public_id}/re-evaluation-requests")
async def request_re_evaluation(
    public_id: UUID,
    payload: ReEvaluationRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit a re-evaluation request for a locked evaluation."""
    service = EvaluationService(db)
    return await service.request_re_evaluation(
        public_id, reason=payload.reason, current_user=current_user
    )


@router.post(
    "/re-evaluation-requests/{request_public_id}/approve",
    response_model=EvaluationResponse,
)
async def approve_re_evaluation(
    request_public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Approve re-evaluation request, create snapshot version, and unlock evaluation."""
    service = EvaluationService(db)
    return await service.approve_re_evaluation(
        request_public_id, current_user=current_user
    )
