"""
Analytics Engine module — FastAPI Router (Phase 16 §9).

Endpoints:
  GET /analytics/ping                       — Module health ping.
  GET /analytics/student/{student_id}       — Get student performance analytics dashboard.
  GET /analytics/class/{class_id}/{exam_id} — Get class-level exam analytics.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics Engine"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "analytics"}


@router.get("/student/{student_id}")
async def get_student_dashboard(
    student_id: int,
    subject_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Get performance analytics dashboard for a student."""
    service = AnalyticsService(db)
    return await service.get_student_dashboard(student_id, subject_id=subject_id)


@router.get("/class/{class_id}/{exam_id}")
async def get_class_analytics(
    class_id: int,
    exam_id: int,
    subject_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Get class-level exam performance analytics."""
    service = AnalyticsService(db)
    return await service.get_class_analytics(
        class_id=class_id, exam_id=exam_id, subject_id=subject_id
    )
