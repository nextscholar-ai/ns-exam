"""
Question Bank module - Service layer.

Orchestrates business logic for question creation, duplicate checking, DOCX import,
versioning, search, status transitions, and performance statistics.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser
from app.modules.question_bank.domain.duplicate_detection import (
    DuplicateResult,
    check_duplicate_candidate,
)
from app.modules.question_bank.domain.versioning import (
    create_question_snapshot,
    increment_version,
)
from app.modules.question_bank.parsing.docx_parser import parse_docx_bytes
from app.modules.question_bank.repository import (
    FillBlankQuestionRepository,
    ObjectiveQuestionRepository,
    QuestionSearchRepository,
    QuestionStatisticsRepository,
    QuestionVersionRepository,
    SubjectiveQuestionRepository,
)
from app.modules.question_bank.schemas import (
    FillBlankQuestionCreate,
    ObjectiveQuestionCreate,
    QuestionSearchFilters,
    SubjectiveQuestionCreate,
)

logger = get_logger(__name__)


class QuestionBankService:
    """Service layer for Question Bank domain."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.obj_repo = ObjectiveQuestionRepository(session)
        self.subj_repo = SubjectiveQuestionRepository(session)
        self.fill_repo = FillBlankQuestionRepository(session)
        self.version_repo = QuestionVersionRepository(session)
        self.stats_repo = QuestionStatisticsRepository(session)
        self.search_repo = QuestionSearchRepository(session)

    # -------------------------------------------------------- Objective --
    async def create_objective_question(
        self,
        data: ObjectiveQuestionCreate,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        # Validate options and correct option
        labels = [opt.label for opt in data.options]
        if data.correct_option not in labels:
            raise ValidationError(
                f"correct_option '{data.correct_option}' must be present in options labels: {labels}"
            )
        if data.marks <= 0:
            raise ValidationError("marks must be greater than 0")

        # Check duplicates
        candidates = await self.obj_repo.get_many(
            filters={
                "board_id": data.board_id,
                "subject_id": data.subject_id,
                "primary_chapter_id": data.primary_chapter_id,
            },
            current_user=current_user,
        )
        cand_dicts = [
            {"id": c.id, "public_id": str(c.public_id), "question_text": c.question_text}
            for c in candidates
        ]
        dup_res = check_duplicate_candidate(data.question_text, cand_dicts)
        if dup_res.is_duplicate:
            logger.warning(
                "question_bank.duplicate_detected",
                match_type=dup_res.match_type,
                score=dup_res.score,
            )

        # Create record
        group_id = int(data.board_id) * 100000 + int(data.primary_chapter_id) * 100 + 1
        obj_dict = {
            "question_group_id": group_id,
            "board_id": data.board_id,
            "class_id": data.class_id,
            "subject_id": data.subject_id,
            "primary_chapter_id": data.primary_chapter_id,
            "primary_unit_id": data.primary_unit_id,
            "primary_topic_id": data.primary_topic_id,
            "question_text": data.question_text,
            "options_json": [opt.model_dump() for opt in data.options],
            "correct_option": data.correct_option,
            "explanation_text": data.explanation_text,
            "difficulty": data.difficulty,
            "bloom_level": data.bloom_level,
            "marks": data.marks,
            "status": "DRAFT",
            "version_no": 1,
        }
        question = await self.obj_repo.create(obj_dict)

        # Create version v1 snapshot
        snapshot = create_question_snapshot("OBJECTIVE", obj_dict)
        await self.version_repo.create({
            "question_type": "OBJECTIVE",
            "question_id": question.id,
            "version_no": 1,
            "snapshot_json": snapshot,
            "change_reason": "Initial creation",
            "is_current": True,
        })

        # Initialize statistics
        await self.stats_repo.create({
            "question_type": "OBJECTIVE",
            "question_id": question.id,
            "usage_count": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "correct_percentage": 0.0,
            "paper_count": 0,
            "student_count": 0,
        })

        logger.info("question_bank.objective_created", public_id=str(question.public_id))
        return self._format_question("OBJECTIVE", question)

    # -------------------------------------------------------- Subjective --
    async def create_subjective_question(
        self,
        data: SubjectiveQuestionCreate,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        if data.max_marks <= 0:
            raise ValidationError("max_marks must be greater than 0")

        group_id = int(data.board_id) * 100000 + int(data.primary_chapter_id) * 100 + 2
        subj_dict = {
            "question_group_id": group_id,
            "board_id": data.board_id,
            "class_id": data.class_id,
            "subject_id": data.subject_id,
            "primary_chapter_id": data.primary_chapter_id,
            "primary_unit_id": data.primary_unit_id,
            "primary_topic_id": data.primary_topic_id,
            "question_text": data.question_text,
            "model_answer_text": data.model_answer_text,
            "max_marks": data.max_marks,
            "expected_key_points_json": data.expected_key_points or [],
            "difficulty": data.difficulty,
            "bloom_level": data.bloom_level,
            "status": "DRAFT",
            "version_no": 1,
        }
        question = await self.subj_repo.create(subj_dict)

        snapshot = create_question_snapshot("SUBJECTIVE", subj_dict)
        await self.version_repo.create({
            "question_type": "SUBJECTIVE",
            "question_id": question.id,
            "version_no": 1,
            "snapshot_json": snapshot,
            "change_reason": "Initial creation",
            "is_current": True,
        })

        await self.stats_repo.create({
            "question_type": "SUBJECTIVE",
            "question_id": question.id,
            "usage_count": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "correct_percentage": 0.0,
            "paper_count": 0,
            "student_count": 0,
        })

        logger.info("question_bank.subjective_created", public_id=str(question.public_id))
        return self._format_question("SUBJECTIVE", question)

    # -------------------------------------------------------- Fill Blank --
    async def create_fill_blank_question(
        self,
        data: FillBlankQuestionCreate,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        if data.marks <= 0:
            raise ValidationError("marks must be greater than 0")

        group_id = int(data.board_id) * 100000 + int(data.primary_chapter_id) * 100 + 3
        fill_dict = {
            "question_group_id": group_id,
            "board_id": data.board_id,
            "class_id": data.class_id,
            "subject_id": data.subject_id,
            "primary_chapter_id": data.primary_chapter_id,
            "primary_unit_id": data.primary_unit_id,
            "primary_topic_id": data.primary_topic_id,
            "question_text_with_blanks": data.question_text_with_blanks,
            "correct_answers_json": data.correct_answers,
            "marks": data.marks,
            "difficulty": data.difficulty,
            "bloom_level": data.bloom_level,
            "status": "DRAFT",
            "version_no": 1,
        }
        question = await self.fill_repo.create(fill_dict)

        snapshot = create_question_snapshot("FILL_BLANK", fill_dict)
        await self.version_repo.create({
            "question_type": "FILL_BLANK",
            "question_id": question.id,
            "version_no": 1,
            "snapshot_json": snapshot,
            "change_reason": "Initial creation",
            "is_current": True,
        })

        await self.stats_repo.create({
            "question_type": "FILL_BLANK",
            "question_id": question.id,
            "usage_count": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "correct_percentage": 0.0,
            "paper_count": 0,
            "student_count": 0,
        })

        logger.info("question_bank.fill_blank_created", public_id=str(question.public_id))
        return self._format_question("FILL_BLANK", question)

    # ------------------------------------------------------------ Import --
    async def import_from_docx(
        self,
        file_bytes: bytes,
        board_id: int,
        class_id: int,
        subject_id: int,
        primary_chapter_id: int,
        current_user: CurrentUser | None = None,
    ) -> list[dict[str, Any]]:
        parsed_items = parse_docx_bytes(file_bytes)
        created_questions = []

        for item in parsed_items:
            data = ObjectiveQuestionCreate(
                board_id=board_id,
                class_id=class_id,
                subject_id=subject_id,
                primary_chapter_id=primary_chapter_id,
                question_text=item.question_text,
                options=item.options,  # type: ignore[arg-type]
                correct_option=item.correct_option,
                explanation_text=item.explanation_text,
                difficulty=item.difficulty,
                bloom_level=item.bloom_level,
                marks=item.marks,
            )
            q = await self.create_objective_question(data, current_user)
            created_questions.append(q)

        return created_questions

    # ------------------------------------------------------------ Lookup --
    async def get_question_by_public_id(
        self, public_id: UUID, current_user: CurrentUser | None = None
    ) -> dict[str, Any]:
        # 1. Search in objective
        obj = await self.obj_repo.get_by_public_id(public_id, current_user=current_user)
        if obj:
            return self._format_question("OBJECTIVE", obj)

        # 2. Search in subjective
        subj = await self.subj_repo.get_by_public_id(public_id, current_user=current_user)
        if subj:
            return self._format_question("SUBJECTIVE", subj)

        # 3. Search in fill blank
        fill = await self.fill_repo.get_by_public_id(public_id, current_user=current_user)
        if fill:
            return self._format_question("FILL_BLANK", fill)

        raise NotFoundError(f"Question with public_id '{public_id}' not found")

    # ------------------------------------------------------------ Search --
    async def search_questions(
        self, filters: QuestionSearchFilters, current_user: CurrentUser | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        return await self.search_repo.search_questions(
            board_id=filters.board_id,
            class_id=filters.class_id,
            subject_id=filters.subject_id,
            primary_chapter_id=filters.primary_chapter_id,
            difficulty=filters.difficulty,
            bloom_level=filters.bloom_level,
            status=filters.status or "ACTIVE",
            keyword=filters.keyword,
            page=filters.page,
            page_size=filters.page_size,
            current_user=current_user,
        )

    # -------------------------------------------------------- Versioning --
    async def create_version(
        self,
        public_id: UUID,
        change_reason: str,
        updated_data: dict[str, Any],
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        # Locate entity
        q_data = await self.get_question_by_public_id(public_id, current_user)
        q_type = q_data["question_type"]

        if q_type == "OBJECTIVE":
            repo = self.obj_repo
        elif q_type == "SUBJECTIVE":
            repo = self.subj_repo
        else:
            repo = self.fill_repo

        question = await repo.get_by_public_id(public_id, current_user=current_user)
        if not question:
            raise NotFoundError(f"Question {public_id} not found")

        next_ver = increment_version(question.version_no)
        updated_dict = dict(updated_data)
        updated_dict["version_no"] = next_ver

        await repo.update(question.id, updated_dict)
        refetched = await repo.get_by_id(question.id)

        # Save new version snapshot
        snap = create_question_snapshot(q_type, updated_dict)
        version_entry = await self.version_repo.create({
            "question_type": q_type,
            "question_id": question.id,
            "version_no": next_ver,
            "snapshot_json": snap,
            "change_reason": change_reason,
            "is_current": True,
        })

        return {
            "public_id": version_entry.public_id,
            "question_type": q_type,
            "version_no": next_ver,
            "snapshot_json": snap,
            "change_reason": change_reason,
            "is_current": True,
            "created_at": version_entry.created_at,
        }

    async def get_version_history(
        self, public_id: UUID, current_user: CurrentUser | None = None
    ) -> list[dict[str, Any]]:
        q_data = await self.get_question_by_public_id(public_id, current_user)
        q_type = q_data["question_type"]

        if q_type == "OBJECTIVE":
            question = await self.obj_repo.get_by_public_id(public_id, current_user=current_user)
        elif q_type == "SUBJECTIVE":
            question = await self.subj_repo.get_by_public_id(public_id, current_user=current_user)
        else:
            question = await self.fill_repo.get_by_public_id(public_id, current_user=current_user)

        if not question:
            raise NotFoundError("Question not found")

        versions = await self.version_repo.get_versions_for_question(q_type, question.id)
        return [
            {
                "public_id": v.public_id,
                "question_type": v.question_type,
                "version_no": v.version_no,
                "snapshot_json": v.snapshot_json,
                "change_reason": v.change_reason,
                "is_current": v.is_current,
                "created_at": v.created_at,
            }
            for v in versions
        ]

    # --------------------------------------------------- Status Change --
    async def change_status(
        self, public_id: UUID, new_status: str, current_user: CurrentUser | None = None
    ) -> dict[str, Any]:
        q_data = await self.get_question_by_public_id(public_id, current_user)
        q_type = q_data["question_type"]

        if q_type == "OBJECTIVE":
            repo = self.obj_repo
        elif q_type == "SUBJECTIVE":
            repo = self.subj_repo
        else:
            repo = self.fill_repo

        question = await repo.get_by_public_id(public_id, current_user=current_user)
        if not question:
            raise NotFoundError("Question not found")

        if question.status == "NEEDS_REVIEW" and new_status == "ACTIVE":
            raise BusinessRuleError("Cannot transition from NEEDS_REVIEW directly to ACTIVE without review confirmation")

        await repo.update(question.id, {"status": new_status})
        updated = await repo.get_by_id(question.id)
        return self._format_question(q_type, updated)

    # ------------------------------------------------------ Statistics --
    async def get_question_statistics(
        self, public_id: UUID, current_user: CurrentUser | None = None
    ) -> dict[str, Any]:
        q_data = await self.get_question_by_public_id(public_id, current_user)
        q_type = q_data["question_type"]

        if q_type == "OBJECTIVE":
            q = await self.obj_repo.get_by_public_id(public_id, current_user=current_user)
        elif q_type == "SUBJECTIVE":
            q = await self.subj_repo.get_by_public_id(public_id, current_user=current_user)
        else:
            q = await self.fill_repo.get_by_public_id(public_id, current_user=current_user)

        if not q:
            raise NotFoundError("Question not found")

        stats = await self.stats_repo.get_by_question(q_type, q.id)
        if not stats:
            return {
                "question_type": q_type,
                "question_id": q.id,
                "usage_count": 0,
                "correct_count": 0,
                "wrong_count": 0,
                "correct_percentage": 0.0,
                "paper_count": 0,
                "student_count": 0,
                "last_used_at": None,
            }

        return {
            "question_type": stats.question_type,
            "question_id": stats.question_id,
            "usage_count": stats.usage_count,
            "correct_count": stats.correct_count,
            "wrong_count": stats.wrong_count,
            "correct_percentage": float(stats.correct_percentage),
            "paper_count": stats.paper_count,
            "student_count": stats.student_count,
            "last_used_at": stats.last_used_at,
        }

    # ---------------------------------------------------- Helper format --
    def _format_question(self, q_type: str, item: Any) -> dict[str, Any]:
        res = {
            "id": item.id,
            "public_id": item.public_id,
            "question_type": q_type,
            "question_group_id": item.question_group_id,
            "board_id": item.board_id,
            "class_id": item.class_id,
            "subject_id": item.subject_id,
            "primary_chapter_id": item.primary_chapter_id,
            "primary_unit_id": item.primary_unit_id,
            "primary_topic_id": item.primary_topic_id,
            "difficulty": item.difficulty,
            "bloom_level": item.bloom_level,
            "status": item.status,
            "version_no": item.version_no,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

        if q_type == "OBJECTIVE":
            res["question_text"] = item.question_text
            res["options"] = item.options_json
            res["correct_option"] = item.correct_option
            res["explanation_text"] = item.explanation_text
            res["marks"] = float(item.marks)
        elif q_type == "SUBJECTIVE":
            res["question_text"] = item.question_text
            res["model_answer_text"] = item.model_answer_text
            res["max_marks"] = float(item.max_marks)
            res["expected_key_points"] = item.expected_key_points_json
            res["marks"] = float(item.max_marks)
        elif q_type == "FILL_BLANK":
            res["question_text"] = item.question_text_with_blanks
            res["correct_answers"] = item.correct_answers_json
            res["marks"] = float(item.marks)

        return res
