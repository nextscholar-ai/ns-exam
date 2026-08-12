"""
Recommendation Engine module — FastAPI Router (Phase 15 §9).

Endpoints:
  GET  /recommendation/ping                                — Module health ping.
  POST /recommendation/generate/{student_id}                — Generate recommendation.
  GET  /recommendation/student/{student_id}                 — List student recommendations.
  POST /recommendation/{public_id}/accept                   — Accept recommendation.
  POST /recommendation/{public_id}/dismiss                  — Dismiss recommendation.
  POST /recommendation/{public_id}/feedback                 — Submit feedback.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.recommendation.schemas import (
    RecommendationFeedbackCreate,
    RecommendationGenerateRequest,
)
from app.modules.recommendation.service import RecommendationService

router = APIRouter(prefix="/recommendation", tags=["Recommendation Engine"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "recommendation"}


@router.post("/generate/{student_id}", status_code=201)
async def generate_recommendation(
    student_id: int,
    payload: RecommendationGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate a personalized practice set / mock exam recommendation."""
    service = RecommendationService(db)
    return await service.generate_recommendation(
        student_id=student_id,
        subject_id=payload.subject_id,
        recommendation_type=payload.recommendation_type,
        item_count=payload.item_count,
        target_difficulty=payload.target_difficulty,
    )


@router.get("/student/{student_id}")
async def list_student_recommendations(
    student_id: int,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List recommendations for a student."""
    service = RecommendationService(db)
    return await service.list_student_recommendations(student_id, status=status)


@router.post("/{public_id}/accept")
async def accept_recommendation(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Accept a practice recommendation (RECOMMENDED → ACCEPTED)."""
    service = RecommendationService(db)
    return await service.accept_recommendation(public_id)


@router.post("/{public_id}/dismiss")
async def dismiss_recommendation(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Dismiss a practice recommendation (RECOMMENDED → DISMISSED)."""
    service = RecommendationService(db)
    return await service.dismiss_recommendation(public_id)


@router.post("/{public_id}/feedback")
async def submit_feedback(
    public_id: UUID,
    payload: RecommendationFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit student or teacher feedback on recommendation quality."""
    service = RecommendationService(db)
    return await service.submit_feedback(
        public_id,
        rating=payload.rating,
        comments=payload.comments,
        current_user=current_user,
    )
