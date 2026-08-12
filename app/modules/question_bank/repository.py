"""
Question Bank module - Repository layer.

Provides type-specific repositories inheriting `BaseRepository`, plus
`QuestionSearchRepository` for cross-type filtered search operations.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.core.security.rbac import CurrentUser
from app.modules.question_bank.models import (
    FillBlankQuestion,
    ObjectiveQuestion,
    QuestionFile,
    QuestionStatistics,
    QuestionVersion,
    SubjectiveQuestion,
)


class BaseQuestionRepository(BaseRepository):
    """Base repository for Question Bank models with board-level scoping support."""

    def _apply_scope(self, stmt: Select, current_user: CurrentUser | None) -> Select:
        """
        Question Bank is board-level (Phase 8 §5.1 & Phase 10 §14).
        Scopes by board_id when current_user carries board_id.
        SUPER_ADMIN / ADMIN roles bypass board scoping.
        """
        if current_user is None or current_user.has_role("SUPER_ADMIN", "ADMIN"):
            return stmt

        if current_user.board_id is not None and hasattr(self.model, "board_id"):
            return stmt.where(self.model.board_id == current_user.board_id)

        return stmt



class ObjectiveQuestionRepository(BaseQuestionRepository):
    ALLOWED_SORT_FIELDS = {"created_at": ObjectiveQuestion.created_at, "marks": ObjectiveQuestion.marks}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ObjectiveQuestion)


class SubjectiveQuestionRepository(BaseQuestionRepository):
    ALLOWED_SORT_FIELDS = {"created_at": SubjectiveQuestion.created_at, "max_marks": SubjectiveQuestion.max_marks}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SubjectiveQuestion)


class FillBlankQuestionRepository(BaseQuestionRepository):
    ALLOWED_SORT_FIELDS = {"created_at": FillBlankQuestion.created_at, "marks": FillBlankQuestion.marks}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FillBlankQuestion)


class QuestionVersionRepository(BaseRepository[QuestionVersion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuestionVersion)

    async def get_versions_for_question(
        self, question_type: str, question_id: int
    ) -> list[QuestionVersion]:
        stmt = (
            select(QuestionVersion)
            .where(
                QuestionVersion.question_type == question_type,
                QuestionVersion.question_id == question_id,
                QuestionVersion.is_deleted.is_(False),
            )
            .order_by(QuestionVersion.version_no.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class QuestionStatisticsRepository(BaseRepository[QuestionStatistics]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, QuestionStatistics)

    async def get_by_question(
        self, question_type: str, question_id: int
    ) -> QuestionStatistics | None:
        stmt = select(QuestionStatistics).where(
            QuestionStatistics.question_type == question_type,
            QuestionStatistics.question_id == question_id,
            QuestionStatistics.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class QuestionSearchRepository:
    """
    Cross-type search repository executing ordered filter chain across
    objective, subjective, and fill-in-blank question tables.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self, filters: Any, current_user: CurrentUser | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        return await self.search_questions(
            board_id=getattr(filters, "board_id", None),
            class_id=getattr(filters, "class_id", None),
            subject_id=getattr(filters, "subject_id", None),
            primary_chapter_id=getattr(filters, "primary_chapter_id", None),
            difficulty=getattr(filters, "difficulty", None),
            bloom_level=getattr(filters, "bloom_level", None),
            status=getattr(filters, "status", "ACTIVE") or "ACTIVE",
            keyword=getattr(filters, "keyword", None),
            page=getattr(filters, "page", 1),
            page_size=getattr(filters, "page_size", 20),
            current_user=current_user,
        )

    async def search_questions(
        self,
        board_id: int | None = None,
        class_id: int | None = None,
        subject_id: int | None = None,
        primary_chapter_id: int | None = None,
        difficulty: str | None = None,
        bloom_level: str | None = None,
        status: str = "ACTIVE",
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        current_user: CurrentUser | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        all_results: list[dict[str, Any]] = []

        # 1. Search Objective Questions
        obj_repo = ObjectiveQuestionRepository(self.session)
        obj_filters: dict[str, Any] = {"is_deleted": False}
        if board_id:
            obj_filters["board_id"] = board_id
        if class_id:
            obj_filters["class_id"] = class_id
        if subject_id:
            obj_filters["subject_id"] = subject_id
        if primary_chapter_id:
            obj_filters["primary_chapter_id"] = primary_chapter_id
        if difficulty:
            obj_filters["difficulty"] = difficulty
        if bloom_level:
            obj_filters["bloom_level"] = bloom_level
        if status:
            obj_filters["status"] = status

        if keyword:
            obj_items = await obj_repo.search(term=keyword, fields=["question_text"], limit=100, current_user=current_user)
        else:
            obj_items = await obj_repo.get_many(filters=obj_filters, current_user=current_user)

        for item in obj_items:
            all_results.append({
                "id": item.id,
                "public_id": item.public_id,
                "question_type": "OBJECTIVE",
                "question_group_id": item.question_group_id,
                "board_id": item.board_id,
                "class_id": item.class_id,
                "subject_id": item.subject_id,
                "primary_chapter_id": item.primary_chapter_id,
                "primary_unit_id": item.primary_unit_id,
                "primary_topic_id": item.primary_topic_id,
                "question_text": item.question_text,
                "options": item.options_json,
                "correct_option": item.correct_option,
                "explanation_text": item.explanation_text,
                "marks": float(item.marks),
                "difficulty": item.difficulty,
                "bloom_level": item.bloom_level,
                "status": item.status,
                "version_no": item.version_no,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            })

        # 2. Search Subjective Questions
        subj_repo = SubjectiveQuestionRepository(self.session)
        subj_filters = dict(obj_filters)
        if keyword:
            subj_items = await subj_repo.search(term=keyword, fields=["question_text"], limit=100, current_user=current_user)
        else:
            subj_items = await subj_repo.get_many(filters=subj_filters, current_user=current_user)

        for item in subj_items:
            all_results.append({
                "id": item.id,
                "public_id": item.public_id,
                "question_type": "SUBJECTIVE",
                "question_group_id": item.question_group_id,
                "board_id": item.board_id,
                "class_id": item.class_id,
                "subject_id": item.subject_id,
                "primary_chapter_id": item.primary_chapter_id,
                "primary_unit_id": item.primary_unit_id,
                "primary_topic_id": item.primary_topic_id,
                "question_text": item.question_text,
                "model_answer_text": item.model_answer_text,
                "max_marks": float(item.max_marks),
                "expected_key_points": item.expected_key_points_json,
                "marks": float(item.max_marks),
                "difficulty": item.difficulty,
                "bloom_level": item.bloom_level,
                "status": item.status,
                "version_no": item.version_no,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            })

        # 3. Search Fill Blank Questions
        fill_repo = FillBlankQuestionRepository(self.session)
        fill_filters = dict(obj_filters)
        if keyword:
            fill_items = await fill_repo.search(term=keyword, fields=["question_text_with_blanks"], limit=100, current_user=current_user)
        else:
            fill_items = await fill_repo.get_many(filters=fill_filters, current_user=current_user)

        for item in fill_items:
            all_results.append({
                "id": item.id,
                "public_id": item.public_id,
                "question_type": "FILL_BLANK",
                "question_group_id": item.question_group_id,
                "board_id": item.board_id,
                "class_id": item.class_id,
                "subject_id": item.subject_id,
                "primary_chapter_id": item.primary_chapter_id,
                "primary_unit_id": item.primary_unit_id,
                "primary_topic_id": item.primary_topic_id,
                "question_text": item.question_text_with_blanks,
                "correct_answers": item.correct_answers_json,
                "marks": float(item.marks),
                "difficulty": item.difficulty,
                "bloom_level": item.bloom_level,
                "status": item.status,
                "version_no": item.version_no,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            })

        total = len(all_results)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_items = all_results[start:end]

        return paginated_items, total
