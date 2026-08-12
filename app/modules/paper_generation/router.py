"""
Paper Generation module — FastAPI router (Phase 11).

All endpoints delegate to PaperGenerationService; no business logic here.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.paper_generation.schemas import (
    PaperApproveRequest,
    PaperGenerateRequest,
    PaperResponse,
)
from app.modules.paper_generation.service import PaperGenerationService

router = APIRouter(prefix="/paper_generation", tags=["paper_generation"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "paper_generation"}


@router.post("/papers/generate", response_model=list[PaperResponse], status_code=201)
async def generate_papers(
    payload: PaperGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """
    Generate paper(s) for an exam configuration.
    If student_ids is empty → one shared non-personalized paper.
    Otherwise → one paper per student_id.
    """
    service = PaperGenerationService(db)
    if not payload.student_ids:
        paper = await service.generate_paper(
            exam_configuration_id=payload.exam_configuration_id,
            student_id=None,
            current_user=current_user,
        )
        return [paper]

    papers = []
    for student_id in payload.student_ids:
        paper = await service.generate_paper(
            exam_configuration_id=payload.exam_configuration_id,
            student_id=student_id,
            current_user=current_user,
        )
        papers.append(paper)
    return papers


@router.get("/papers/{public_id}", response_model=PaperResponse)
async def get_paper(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch a paper by public_id."""
    service = PaperGenerationService(db)
    paper = await service._paper_repo.get_by_public_id(public_id)
    if paper is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(f"Paper {public_id} not found")
    return service._paper_to_dict(paper)


@router.post("/papers/{public_id}/approve", response_model=PaperResponse)
async def approve_paper(
    public_id: UUID,
    payload: PaperApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Approve a paper (UNDER_REVIEW → APPROVED)."""
    service = PaperGenerationService(db)
    return await service.approve_paper(
        public_id,
        current_user=current_user,
        notes=payload.notes,
    )


@router.get("/papers/{public_id}/validations")
async def get_paper_validations(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return the latest validation results for a paper."""
    service = PaperGenerationService(db)
    return await service.get_validations(public_id)


@router.get("/papers/{public_id}/ai-explanation")
async def get_ai_explanation(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return AI generation log for all candidate questions (admin/debug)."""
    service = PaperGenerationService(db)
    return await service.get_ai_explanation(public_id)


@router.get("/papers/{public_id}/versions")
async def get_paper_versions(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return version history for a paper."""
    service = PaperGenerationService(db)
    return await service.get_version_history(public_id)
