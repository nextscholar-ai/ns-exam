"""
Question Bank module - FastAPI Router.

Exposes REST API endpoints for question creation, DOCX import, search,
versioning, status transitions, and performance statistics.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.security.rbac import CurrentUser, get_current_user
from app.modules.question_bank.schemas import (
    FillBlankQuestionCreate,
    ObjectiveQuestionCreate,
    QuestionResponse,
    QuestionSearchFilters,
    QuestionStatisticsResponse,
    StatusUpdateRequest,
    SubjectiveQuestionCreate,
    VersionCreateRequest,
    VersionResponse,
)
from app.modules.question_bank.service import QuestionBankService

router = APIRouter(prefix="/question_bank", tags=["questions"])


@router.get("/ping", tags=["ping"])
async def ping() -> dict[str, str]:
    return {"status": "ok", "module": "question_bank"}


@router.post("/objective", response_model=QuestionResponse, status_code=201)
async def create_objective_question(
    payload: ObjectiveQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = QuestionBankService(db)
    return await service.create_objective_question(payload, current_user=current_user)


@router.post("/subjective", response_model=QuestionResponse, status_code=201)
async def create_subjective_question(
    payload: SubjectiveQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = QuestionBankService(db)
    return await service.create_subjective_question(payload, current_user=current_user)


@router.post("/fill-blank", response_model=QuestionResponse, status_code=201)
async def create_fill_blank_question(
    payload: FillBlankQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = QuestionBankService(db)
    return await service.create_fill_blank_question(payload, current_user=current_user)


@router.post("/import", response_model=list[QuestionResponse], status_code=201)
async def import_questions_docx(
    board_id: int = Form(...),
    class_id: int = Form(...),
    subject_id: int = Form(...),
    primary_chapter_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    file_bytes = await file.read()
    service = QuestionBankService(db)
    return await service.import_from_docx(
        file_bytes=file_bytes,
        board_id=board_id,
        class_id=class_id,
        subject_id=subject_id,
        primary_chapter_id=primary_chapter_id,
        current_user=current_user,
    )


@router.get("", response_model=list[QuestionResponse])
async def search_questions(
    board_id: int | None = Query(None),
    class_id: int | None = Query(None),
    subject_id: int | None = Query(None),
    primary_chapter_id: int | None = Query(None),
    difficulty: str | None = Query(None),
    bloom_level: str | None = Query(None),
    status: str = Query("ACTIVE"),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    service = QuestionBankService(db)
    filters = QuestionSearchFilters(
        board_id=board_id,
        class_id=class_id,
        subject_id=subject_id,
        primary_chapter_id=primary_chapter_id,
        difficulty=difficulty,
        bloom_level=bloom_level,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    items, _ = await service.search_questions(filters, current_user=current_user)
    return items


@router.get("/{public_id}", response_model=QuestionResponse)
async def get_question(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = QuestionBankService(db)
    return await service.get_question_by_public_id(public_id, current_user=current_user)


@router.post("/{public_id}/versions", response_model=VersionResponse, status_code=201)
async def create_question_version(
    public_id: UUID,
    payload: VersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = QuestionBankService(db)
    return await service.create_version(
        public_id=public_id,
        change_reason=payload.change_reason,
        updated_data=payload.updated_data,
        current_user=current_user,
    )


@router.get("/{public_id}/versions", response_model=list[VersionResponse])
async def get_question_versions(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    service = QuestionBankService(db)
    return await service.get_version_history(public_id, current_user=current_user)


@router.patch("/{public_id}/status", response_model=QuestionResponse)
async def update_question_status(
    public_id: UUID,
    payload: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = QuestionBankService(db)
    return await service.change_status(public_id, payload.status, current_user=current_user)


@router.get("/{public_id}/statistics", response_model=QuestionStatisticsResponse)
async def get_question_statistics(
    public_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = QuestionBankService(db)
    return await service.get_question_statistics(public_id, current_user=current_user)
