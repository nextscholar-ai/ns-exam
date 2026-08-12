"""
Paper Generation module — Repository layer (Phase 11).

PaperRepository, PaperSectionRepository, PaperQuestionRepository,
PaperVersionRepository, PaperValidationRepository, AIGenerationLogRepository.

Papers are scoped at exam_configuration level (no direct board_id column),
so the default school_id scoping from BaseRepository is bypassed by simply
not adding board/school filters — access control is enforced at the service
layer via exam_configuration ownership checks (Phase 11 §14).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.paper_generation.models import (
    AIGenerationLog,
    Paper,
    PaperQuestion,
    PaperSection,
    PaperValidation,
    PaperVersion,
)


class PaperRepository(BaseRepository):
    """CRUD for Paper rows."""

    ALLOWED_SORT_FIELDS = {
        "created_at": Paper.created_at,
        "status": Paper.status,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Paper)

    async def get_by_public_id(self, public_id: UUID) -> Paper | None:
        """Fetch a Paper by its UUID public key."""
        stmt = (
            select(Paper)
            .where(Paper.public_id == str(public_id))
            .where(Paper.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_exam_config(
        self,
        exam_configuration_id: int,
    ) -> list[Paper]:
        """All non-deleted papers for an exam configuration."""
        stmt = (
            select(Paper)
            .where(Paper.exam_configuration_id == exam_configuration_id)
            .where(Paper.is_deleted == False)  # noqa: E712
            .order_by(Paper.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PaperSectionRepository(BaseRepository):
    """CRUD for PaperSection rows."""

    ALLOWED_SORT_FIELDS = {"section_label": PaperSection.section_label}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaperSection)

    async def list_by_paper(self, paper_id: int) -> list[PaperSection]:
        stmt = (
            select(PaperSection)
            .where(PaperSection.paper_id == paper_id)
            .where(PaperSection.is_deleted == False)  # noqa: E712
            .order_by(PaperSection.section_label)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PaperQuestionRepository(BaseRepository):
    """CRUD for PaperQuestion rows."""

    ALLOWED_SORT_FIELDS = {"sequence_no": PaperQuestion.sequence_no}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaperQuestion)

    async def list_by_section(self, paper_section_id: int) -> list[PaperQuestion]:
        stmt = (
            select(PaperQuestion)
            .where(PaperQuestion.paper_section_id == paper_section_id)
            .where(PaperQuestion.is_deleted == False)  # noqa: E712
            .order_by(PaperQuestion.sequence_no)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PaperVersionRepository(BaseRepository):
    """CRUD for PaperVersion rows."""

    ALLOWED_SORT_FIELDS = {"version_no": PaperVersion.version_no}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaperVersion)

    async def list_by_paper(self, paper_id: int) -> list[PaperVersion]:
        stmt = (
            select(PaperVersion)
            .where(PaperVersion.paper_id == paper_id)
            .order_by(PaperVersion.version_no.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_all_non_current(self, paper_id: int) -> None:
        """Flip is_current=False on all existing versions for paper_id."""
        rows = await self.list_by_paper(paper_id)
        for row in rows:
            row.is_current = False
        await self.session.flush()

    async def next_version_no(self, paper_id: int) -> int:
        """Return the next sequential version number for a paper."""
        rows = await self.list_by_paper(paper_id)
        return (max((r.version_no for r in rows), default=0) + 1)


class PaperValidationRepository(BaseRepository):
    """CRUD for PaperValidation rows."""

    ALLOWED_SORT_FIELDS = {"rule_code": PaperValidation.rule_code}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaperValidation)

    async def list_by_paper(self, paper_id: int) -> list[PaperValidation]:
        stmt = (
            select(PaperValidation)
            .where(PaperValidation.paper_id == paper_id)
            .order_by(PaperValidation.rule_code)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AIGenerationLogRepository(BaseRepository):
    """CRUD for AIGenerationLog rows."""

    ALLOWED_SORT_FIELDS = {"final_rank_score": AIGenerationLog.final_rank_score}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AIGenerationLog)

    async def list_by_paper(self, paper_id: int) -> list[AIGenerationLog]:
        stmt = (
            select(AIGenerationLog)
            .where(AIGenerationLog.paper_id == paper_id)
            .order_by(AIGenerationLog.final_rank_score.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
