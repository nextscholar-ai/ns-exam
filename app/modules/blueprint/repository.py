"""
Blueprint module — Repository layer (Phase 11).

All repositories inherit BaseRepository[ModelT] to get the full generic
CRUD surface for free (get_by_id, paginate, create, update, soft_delete …).

Board-scoped resources (Blueprint, ExamConfiguration) override _apply_scope()
to filter by board_id instead of school_id, consistent with Phase 10's
QuestionBank approach (Phase 8 §5.1).
"""
from __future__ import annotations

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.core.security.rbac import CurrentUser
from app.modules.blueprint.models import (
    Blueprint,
    BlueprintSection,
    ExamConfiguration,
    StudentPaper,
)


class BoardScopedRepository(BaseRepository):
    """
    Mixin base that scopes queries by board_id.

    Reused by BlueprintRepository and ExamConfigRepository so the
    board-scoping logic lives in exactly one place.
    """

    def _apply_scope(
        self,
        stmt: Select,
        current_user: CurrentUser | None,
    ) -> Select:
        """Scope by board_id; SUPER_ADMIN / ADMIN bypass."""
        if current_user is None or current_user.has_role("SUPER_ADMIN", "ADMIN"):
            return stmt
        if (
            current_user.board_id is not None
            and hasattr(self.model, "board_id")
        ):
            stmt = stmt.where(
                self.model.board_id == current_user.board_id
            )
        return stmt


class BlueprintRepository(BoardScopedRepository):
    """CRUD for Blueprint rows."""

    ALLOWED_SORT_FIELDS = {
        "created_at": Blueprint.created_at,
        "name": Blueprint.name,
        "total_marks": Blueprint.total_marks,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Blueprint)


class BlueprintSectionRepository(BaseRepository):
    """CRUD for BlueprintSection rows (no scoping — owned by a Blueprint)."""

    ALLOWED_SORT_FIELDS = {
        "section_label": BlueprintSection.section_label,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BlueprintSection)


class ExamConfigRepository(BoardScopedRepository):
    """CRUD for ExamConfiguration rows."""

    ALLOWED_SORT_FIELDS = {
        "created_at": ExamConfiguration.created_at,
        "exam_name": ExamConfiguration.exam_name,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExamConfiguration)


class StudentPaperRepository(BaseRepository):
    """CRUD for StudentPaper assignment links."""

    ALLOWED_SORT_FIELDS = {"created_at": StudentPaper.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StudentPaper)
