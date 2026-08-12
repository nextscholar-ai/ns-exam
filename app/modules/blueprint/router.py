"""
Blueprint module — FastAPI router (Phase 11).

All endpoints follow Phase 7 §5 conventions:
  - Thin handlers: validate input via Pydantic, delegate to service, return dict.
  - Standard envelope applied by middleware (Phase 7 §4).
  - /ping for health-check registration.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.blueprint.schemas import (
    BlueprintCreate,
    BlueprintResponse,
    ExamConfigCreate,
    ExamConfigResponse,
    StatusUpdateRequest,
)
from app.modules.blueprint.service import BlueprintService

router = APIRouter(prefix="/blueprint", tags=["blueprint"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "blueprint"}


# ---------------------------------------------------------------- Blueprints --

@router.post(
    "/blueprints",
    response_model=BlueprintResponse,
    status_code=201,
)
async def create_blueprint(
    payload: BlueprintCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new blueprint with its sections."""
    service = BlueprintService(db)
    return await service.create_blueprint(payload, current_user=current_user)


@router.get("/blueprints/{public_id}", response_model=BlueprintResponse)
async def get_blueprint(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch a blueprint by public_id."""
    service = BlueprintService(db)
    return await service.get_blueprint(public_id, current_user=current_user)


@router.patch("/blueprints/{public_id}/status", response_model=BlueprintResponse)
async def change_blueprint_status(
    public_id: UUID,
    payload: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Change a blueprint's status (DRAFT → ACTIVE → ARCHIVED)."""
    service = BlueprintService(db)
    return await service.change_blueprint_status(
        public_id,
        payload.status,
        current_user=current_user,
    )


@router.get("/blueprints/{blueprint_id}/sections")
async def get_blueprint_sections(
    blueprint_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return all sections for a blueprint."""
    service = BlueprintService(db)
    return await service.get_sections(blueprint_id)


# -------------------------------------------------------- ExamConfigurations --

@router.post(
    "/exam-configurations",
    response_model=ExamConfigResponse,
    status_code=201,
)
async def create_exam_config(
    payload: ExamConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create an exam configuration linked to an active blueprint."""
    service = BlueprintService(db)
    return await service.create_exam_config(payload, current_user=current_user)


@router.get(
    "/exam-configurations/{public_id}",
    response_model=ExamConfigResponse,
)
async def get_exam_config(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch an exam configuration by public_id."""
    service = BlueprintService(db)
    return await service.get_exam_config(public_id, current_user=current_user)


@router.patch(
    "/exam-configurations/{public_id}/status",
    response_model=ExamConfigResponse,
)
async def change_exam_config_status(
    public_id: UUID,
    payload: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Change exam configuration status."""
    service = BlueprintService(db)
    return await service.change_exam_config_status(
        public_id,
        payload.status,
        current_user=current_user,
    )
