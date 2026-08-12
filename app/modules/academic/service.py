"""
AcademicSnapshotService (Phase 4 §9 / Phase 8 §5.2) — queries the snapshot
tree via the generic `BaseRepository.list()` contract. No SQLAlchemy import
here at all (Phase 8 §8) - every query goes through a repository method.
"""
from __future__ import annotations

from app.core.db.session import DbSession
from app.core.pagination import Page, PageParams, SortParams
from app.modules.academic.repository import (
    BoardRepository,
    ChapterRepository,
    ClassRepository,
    SchoolRepository,
    SubjectRepository,
    TopicRepository,
    UnitRepository,
)
from app.modules.academic.schemas import (
    BoardOut,
    ChapterOut,
    ClassOut,
    SchoolOut,
    SubjectOut,
    TopicOut,
    UnitOut,
)


class AcademicSnapshotService:
    def __init__(self, session: DbSession) -> None:
        self.boards = BoardRepository(session)
        self.schools = SchoolRepository(session)
        self.classes = ClassRepository(session)
        self.subjects = SubjectRepository(session)
        self.chapters = ChapterRepository(session)
        self.units = UnitRepository(session)
        self.topics = TopicRepository(session)

    async def list_boards(
        self, params: PageParams, sort: SortParams, *, status: str | None = None
    ) -> Page[BoardOut]:
        rows, total = await self.boards.list(
            filters={"status": status},
            page=params.page,
            page_size=params.page_size,
            sort_by=sort.sort_by,
            sort_dir=sort.sort_dir,
        )
        return Page(
            items=[BoardOut.model_validate(r) for r in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def list_schools(
        self, params: PageParams, sort: SortParams, *, board_id: int | None = None
    ) -> Page[SchoolOut]:
        rows, total = await self.schools.list(
            filters={"board_id": board_id},
            page=params.page,
            page_size=params.page_size,
            sort_by=sort.sort_by,
            sort_dir=sort.sort_dir,
        )
        return Page(
            items=[SchoolOut.model_validate(r) for r in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def list_classes(
        self, params: PageParams, sort: SortParams, *, school_id: int | None = None
    ) -> Page[ClassOut]:
        rows, total = await self.classes.list(
            filters={"school_id": school_id},
            page=params.page,
            page_size=params.page_size,
            sort_by=sort.sort_by,
            sort_dir=sort.sort_dir,
        )
        return Page(
            items=[ClassOut.model_validate(r) for r in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def list_subjects(
        self,
        params: PageParams,
        sort: SortParams,
        *,
        board_id: int | None = None,
        class_id: int | None = None,
    ) -> Page[SubjectOut]:
        rows, total = await self.subjects.list(
            filters={"board_id": board_id, "class_id": class_id},
            page=params.page,
            page_size=params.page_size,
            sort_by=sort.sort_by,
            sort_dir=sort.sort_dir,
        )
        return Page(
            items=[SubjectOut.model_validate(r) for r in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def list_chapters(
        self, params: PageParams, sort: SortParams, *, subject_id: int | None = None
    ) -> Page[ChapterOut]:
        rows, total = await self.chapters.list(
            filters={"subject_id": subject_id},
            page=params.page,
            page_size=params.page_size,
            sort_by=sort.sort_by,
            sort_dir=sort.sort_dir,
        )
        return Page(
            items=[ChapterOut.model_validate(r) for r in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def list_units(
        self, params: PageParams, sort: SortParams, *, chapter_id: int | None = None
    ) -> Page[UnitOut]:
        rows, total = await self.units.list(
            filters={"chapter_id": chapter_id},
            page=params.page,
            page_size=params.page_size,
            sort_by=sort.sort_by,
            sort_dir=sort.sort_dir,
        )
        return Page(
            items=[UnitOut.model_validate(r) for r in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def list_topics(
        self, params: PageParams, sort: SortParams, *, unit_id: int | None = None
    ) -> Page[TopicOut]:
        rows, total = await self.topics.list(
            filters={"unit_id": unit_id},
            page=params.page,
            page_size=params.page_size,
            sort_by=sort.sort_by,
            sort_dir=sort.sort_dir,
        )
        return Page(
            items=[TopicOut.model_validate(r) for r in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )
