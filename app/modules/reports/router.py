"""
Reporting Engine module — FastAPI Router (Phase 16 §9.5).

Endpoints:
  GET  /reports/ping                               — Module health ping.
  POST /reports/student/{student_id}/generate      — Generate student report card snapshot.
  POST /reports/exam/{exam_id}/generate             — Generate exam analysis report snapshot.
  GET  /reports/{public_id}                        — Get report snapshot by public_id.
  POST /reports/{public_id}/publish                 — Publish report snapshot.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["Reporting Engine"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "reports"}


@router.post("/student/{student_id}/generate", status_code=201)
async def generate_student_report_card(
    student_id: int,
    subject_id: int,
    title: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate and snapshot student progress report card."""
    service = ReportService(db)
    return await service.generate_student_report_card(
        student_id=student_id,
        subject_id=subject_id,
        title=title,
        current_user=current_user,
    )


@router.post("/exam/{exam_id}/generate", status_code=201)
async def generate_exam_analysis_report(
    exam_id: int,
    class_id: int,
    subject_id: int,
    title: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate and snapshot exam analysis report."""
    service = ReportService(db)
    return await service.generate_exam_analysis_report(
        exam_id=exam_id,
        class_id=class_id,
        subject_id=subject_id,
        title=title,
        current_user=current_user,
    )


@router.get("/{public_id}")
async def get_report_snapshot(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch report snapshot by public_id."""
    service = ReportService(db)
    return await service.get_report_by_public_id(public_id)


@router.post("/{public_id}/publish")
async def publish_report(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Publish report snapshot (GENERATED → PUBLISHED)."""
    service = ReportService(db)
    return await service.publish_report(public_id)
