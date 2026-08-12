"""
Exam Management module — FastAPI router (Phase 12).

All endpoints delegate to ExamService and AttemptService.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.exam_management.schemas import (
    AttemptStartRequest,
    AttemptSubmitRequest,
    ExamConfigure,
    ExamCreate,
    ExamResponse,
    ExamSchedule,
    ExamStatusHistoryResponse,
    GuestJoinRequest,
    GuestJoinResponse,
    StudentAttemptResponse,
)
from app.modules.exam_management.service import AttemptService, ExamService

router = APIRouter(prefix="/exam_management", tags=["exam_management"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "exam_management"}


# ---------------------------------------------------------------- Exam Lifecycle --

@router.post("/exams", response_model=ExamResponse, status_code=201)
async def create_exam(
    payload: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new exam in DRAFT status."""
    service = ExamService(db)
    return await service.create_exam(payload, current_user=current_user)


@router.patch("/exams/{public_id}/configure", response_model=ExamResponse)
async def configure_exam(
    public_id: UUID,
    payload: ExamConfigure,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Link exam configuration and transition DRAFT → CONFIGURED."""
    service = ExamService(db)
    return await service.configure_exam(public_id, payload, current_user=current_user)


@router.post("/exams/{public_id}/generate-papers", response_model=ExamResponse)
async def generate_papers(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger paper generation and transition CONFIGURED → PAPER_GENERATED."""
    service = ExamService(db)
    return await service.generate_papers_for_exam(public_id, current_user=current_user)


@router.post("/exams/{public_id}/approve", response_model=ExamResponse)
async def approve_exam(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Approve exam papers → transition to APPROVED."""
    service = ExamService(db)
    return await service.approve_exam(public_id, current_user=current_user)


@router.post("/exams/{public_id}/publish", response_model=ExamResponse)
async def publish_exam(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Publish an approved exam → APPROVED → PUBLISHED (generates join_code)."""
    service = ExamService(db)
    return await service.publish_exam(public_id, current_user=current_user)


@router.post("/exams/{public_id}/schedule", response_model=ExamResponse)
async def schedule_exam(
    public_id: UUID,
    payload: ExamSchedule,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Schedule a published exam → PUBLISHED → SCHEDULED."""
    service = ExamService(db)
    return await service.schedule_exam(public_id, payload, current_user=current_user)


@router.post("/exams/join", response_model=GuestJoinResponse)
async def join_guest(
    payload: GuestJoinRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Guest student join endpoint via join code."""
    service = ExamService(db)
    return await service.join_guest(payload.join_code, payload.guest_name)


@router.get("/exams/{public_id}/status-history", response_model=list[ExamStatusHistoryResponse])
async def get_status_history(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return exam status transition timeline."""
    service = ExamService(db)
    return await service.get_status_history(public_id)


# --------------------------------------------------------------- Attempts --

@router.post("/exams/{public_id}/attempts", response_model=StudentAttemptResponse, status_code=201)
async def start_attempt(
    public_id: UUID,
    payload: AttemptStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Start an exam attempt (Regular: single attempt; Mock: multi-attempt with new paper)."""
    service = AttemptService(db)
    return await service.start_attempt(
        public_id, payload.student_id, current_user=current_user
    )


@router.post("/attempts/{public_id}/submit", response_model=StudentAttemptResponse)
async def submit_attempt(
    public_id: UUID,
    payload: AttemptSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit an in-progress attempt → SUBMITTED (emits ExamSubmitted event)."""
    service = AttemptService(db)
    return await service.submit_attempt(
        public_id,
        answers_summary_json=payload.answers_summary_json,
        current_user=current_user,
    )
