"""
Mastery Engine module — API Router (Phase 14 §9).

Endpoints:
  GET  /learning-profile/{student_id}               — Full learning profile.
  GET  /learning-profile/{student_id}/weak-topics   — List of weak topic IDs.
  GET  /learning-profile/{student_id}/history/{topic_id} — Mastery history for a topic.
  POST /learning-profile/{student_id}/process/{evaluation_public_id} — Trigger mastery update.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import get_current_user
from app.modules.learning_profile.service import LearningProfileService, MasteryService

router = APIRouter(prefix="/learning_profile", tags=["Learning Profile"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "learning_profile"}


@router.get(
    "/{student_id}",
    summary="Get full learning profile for a student",
    dependencies=[Depends(get_current_user)],
)
async def get_learning_profile(
    student_id: int,
    subject_id: int | None = None,
    session: AsyncSession = Depends(get_db),
):
    service = LearningProfileService(session)
    return await service.get_learning_profile(student_id, subject_id=subject_id)


@router.get(
    "/{student_id}/weak-topics",
    summary="Get weak topic IDs for a student",
    dependencies=[Depends(get_current_user)],
)
async def get_weak_topics(
    student_id: int,
    subject_id: int | None = None,
    session: AsyncSession = Depends(get_db),
):
    service = LearningProfileService(session)
    weak_ids = await service.get_weak_topics(student_id, subject_id=subject_id)
    return {"student_id": student_id, "weak_topic_ids": weak_ids}


@router.get(
    "/{student_id}/history/{topic_id}",
    summary="Get mastery history for a student × topic",
    dependencies=[Depends(get_current_user)],
)
async def get_topic_mastery_history(
    student_id: int,
    topic_id: int,
    session: AsyncSession = Depends(get_db),
):
    service = LearningProfileService(session)
    history = await service.get_topic_mastery_history(student_id, topic_id)
    return {"student_id": student_id, "topic_id": topic_id, "history": history}


@router.post(
    "/{student_id}/process/{evaluation_public_id}",
    summary="Trigger mastery update from a locked evaluation",
    dependencies=[Depends(get_current_user)],
)
async def process_evaluation_mastery(
    student_id: int,
    evaluation_public_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = MasteryService(session)
    return await service.process_evaluation(evaluation_public_id)
