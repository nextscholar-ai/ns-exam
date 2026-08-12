"""
Academic module router (Phase 4 §8 / Phase 7 exit criteria).

Read-only snapshot tree - no auth required for browsing reference data
(boards/schools/classes/subjects/chapters/units/topics never contain
anything sensitive). Every list endpoint follows the Phase 7 §5.1-§5.5
contract: explicit `response_model`, `summary`, documented `responses`,
shared pagination + whitelisted sorting, explicit typed filter params.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.pagination import Page, PageParams, SortParams, pagination_query, sorting_query
from app.modules.academic.schemas import (
    BoardOut,
    ChapterOut,
    ClassOut,
    SchoolOut,
    SubjectOut,
    TopicOut,
    UnitOut,
)
from app.modules.academic.service import AcademicSnapshotService

router = APIRouter(prefix="/academic", tags=["academic"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"module": "academic", "status": "ok"}


@router.get(
    "/boards",
    response_model=Page[BoardOut],
    summary="List boards (paginated, sortable by name/created_at)",
    responses={422: {"description": "Invalid sort_by field"}},
)
async def list_boards(
    status: str | None = None,
    params: PageParams = Depends(pagination_query),
    sort: SortParams = Depends(sorting_query),
    db: AsyncSession = Depends(get_db),
) -> Page[BoardOut]:
    return await AcademicSnapshotService(db).list_boards(params, sort, status=status)


@router.get(
    "/schools",
    response_model=Page[SchoolOut],
    summary="List schools (paginated, filterable by board_id)",
    responses={422: {"description": "Invalid sort_by field"}},
)
async def list_schools(
    board_id: int | None = None,
    params: PageParams = Depends(pagination_query),
    sort: SortParams = Depends(sorting_query),
    db: AsyncSession = Depends(get_db),
) -> Page[SchoolOut]:
    return await AcademicSnapshotService(db).list_schools(params, sort, board_id=board_id)


@router.get(
    "/classes",
    response_model=Page[ClassOut],
    summary="List classes (paginated, filterable by school_id)",
    responses={422: {"description": "Invalid sort_by field"}},
)
async def list_classes(
    school_id: int | None = None,
    params: PageParams = Depends(pagination_query),
    sort: SortParams = Depends(sorting_query),
    db: AsyncSession = Depends(get_db),
) -> Page[ClassOut]:
    return await AcademicSnapshotService(db).list_classes(params, sort, school_id=school_id)


@router.get(
    "/subjects",
    response_model=Page[SubjectOut],
    summary="List subjects (paginated, filterable by board_id/class_id)",
    responses={422: {"description": "Invalid sort_by field"}},
)
async def list_subjects(
    board_id: int | None = None,
    class_id: int | None = None,
    params: PageParams = Depends(pagination_query),
    sort: SortParams = Depends(sorting_query),
    db: AsyncSession = Depends(get_db),
) -> Page[SubjectOut]:
    return await AcademicSnapshotService(db).list_subjects(
        params, sort, board_id=board_id, class_id=class_id
    )


@router.get(
    "/chapters",
    response_model=Page[ChapterOut],
    summary="List chapters (paginated, filterable by subject_id)",
    responses={422: {"description": "Invalid sort_by field"}},
)
async def list_chapters(
    subject_id: int | None = None,
    params: PageParams = Depends(pagination_query),
    sort: SortParams = Depends(sorting_query),
    db: AsyncSession = Depends(get_db),
) -> Page[ChapterOut]:
    return await AcademicSnapshotService(db).list_chapters(params, sort, subject_id=subject_id)


@router.get(
    "/units",
    response_model=Page[UnitOut],
    summary="List units (paginated, filterable by chapter_id)",
    responses={422: {"description": "Invalid sort_by field"}},
)
async def list_units(
    chapter_id: int | None = None,
    params: PageParams = Depends(pagination_query),
    sort: SortParams = Depends(sorting_query),
    db: AsyncSession = Depends(get_db),
) -> Page[UnitOut]:
    return await AcademicSnapshotService(db).list_units(params, sort, chapter_id=chapter_id)


@router.get(
    "/topics",
    response_model=Page[TopicOut],
    summary="List topics (paginated, filterable by unit_id)",
    responses={422: {"description": "Invalid sort_by field"}},
)
async def list_topics(
    unit_id: int | None = None,
    params: PageParams = Depends(pagination_query),
    sort: SortParams = Depends(sorting_query),
    db: AsyncSession = Depends(get_db),
) -> Page[TopicOut]:
    return await AcademicSnapshotService(db).list_topics(params, sort, unit_id=unit_id)
