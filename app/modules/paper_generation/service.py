"""
Paper Generation module — Service layer (Phase 11).

Orchestrates the full paper generation lifecycle:
  1. Validate blueprint + exam config.
  2. Build CandidateFetcher closure (read-only QB call).
  3. Run ConstraintEngine.assemble_paper().
  4. Persist Paper + PaperSection + PaperQuestion rows.
  5. Write AIGenerationLog rows for explainability.
  6. Run all validation rules (validation.py).
  7. Persist PaperValidation rows.
  8. Teacher review: replace question / approve.
  9. Versioning: create PaperVersion snapshot on any edit.

Cross-module reads:
  - QuestionBankService (Phase 10) — read-only question search.
  - LearningProfileService (Phase 14 stub) — read-only weak topics.
  Both are allowed by Phase 11 §5 dependency-direction ruling.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser
from app.modules.blueprint.repository import (
    BlueprintRepository,
    BlueprintSectionRepository,
    ExamConfigRepository,
)
from app.modules.paper_generation.domain.constraint_engine import (
    AssembledSection,
    ConstraintEngine,
    EngineContext,
)
from app.modules.paper_generation.domain.validation import (
    ValidationResult,
    all_passed,
    run_all_validations,
)
from app.modules.paper_generation.models import (
    AIGenerationLog,
    Paper,
    PaperQuestion,
    PaperSection,
    PaperValidation,
    PaperVersion,
)
from app.modules.paper_generation.repository import (
    AIGenerationLogRepository,
    PaperQuestionRepository,
    PaperRepository,
    PaperSectionRepository,
    PaperValidationRepository,
    PaperVersionRepository,
)
from app.modules.question_bank.repository import QuestionSearchRepository
from app.modules.question_bank.schemas import QuestionSearchFilters

logger = get_logger(__name__)

# Status machine for Paper
_PAPER_TRANSITIONS: dict[str, set[str]] = {
    "GENERATED": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {"APPROVED", "GENERATED"},
    "APPROVED": {"PUBLISHED"},
    "PUBLISHED": set(),          # immutable — requires admin unlock
    "NEEDS_ATTENTION": {"UNDER_REVIEW"},
}


class PaperGenerationService:
    """
    Service for full paper generation and review lifecycle.

    Injected dependencies allow unit testing with DB stubs:
      - All repos passed through __init__.
      - CandidateFetcher is built from QuestionSearchRepository at call time.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Blueprint-side repos (read-only here)
        self._bp_repo = BlueprintRepository(session)
        self._sec_repo = BlueprintSectionRepository(session)
        self._ec_repo = ExamConfigRepository(session)
        # Paper-side repos
        self._paper_repo = PaperRepository(session)
        self._ps_repo = PaperSectionRepository(session)
        self._pq_repo = PaperQuestionRepository(session)
        self._pv_repo = PaperVersionRepository(session)
        self._val_repo = PaperValidationRepository(session)
        self._ai_repo = AIGenerationLogRepository(session)
        # Question bank (cross-module read-only)
        self._qb_search = QuestionSearchRepository(session)

    # ---------------------------------------------------------------- Generation --

    async def generate_paper(
        self,
        exam_configuration_id: int,
        student_id: int | None = None,
        weak_topic_ids: set[int] | None = None,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Generate one paper for a given exam configuration.

        student_id=None  → shared non-personalized paper.
        student_id=N     → personalized paper for that student.
        weak_topic_ids   → passed from LearningProfileService (Phase 14).
        """
        logger.info(
            "Generating paper",
            exam_configuration_id=exam_configuration_id,
            student_id=student_id,
        )

        # Load exam config and blueprint
        ec = await self._ec_repo.get_by_id(exam_configuration_id)
        if ec is None:
            raise NotFoundError(
                f"ExamConfiguration {exam_configuration_id} not found"
            )
        bp = await self._bp_repo.get_by_id(ec.blueprint_id)
        if bp is None:
            raise NotFoundError(f"Blueprint {ec.blueprint_id} not found")

        # Load blueprint sections
        sections_raw = await self._sec_repo.get_many(
            filters={"blueprint_id": bp.id}
        )
        bp_sections_dicts = [self._sec_to_dict(s) for s in sections_raw]

        # Build the chapter_ids scope
        chapter_ids: list[int] = (
            ec.current_chapters_json or []
        )

        # Build constraint engine context
        ctx = EngineContext(
            board_id=bp.board_id,
            class_id=bp.class_id,
            subject_id=bp.subject_id,
            blueprint_total_marks=float(bp.total_marks),
            blueprint_duration=bp.duration_minutes,
            weak_topic_ids=weak_topic_ids or set(),
        )

        # Build the candidate fetcher closure (read-only QB search)
        fetcher = self._build_fetcher()

        # Run the constraint engine
        engine = ConstraintEngine(ctx)
        assembled: list[AssembledSection] = await engine.assemble_paper(
            blueprint_sections=bp_sections_dicts,
            chapter_ids=chapter_ids,
            fetcher=fetcher,
        )

        # Determine total marks from assembled sections
        paper_total = sum(asm.actual_marks for asm in assembled)

        # Persist Paper row
        paper = await self._paper_repo.create(
            {
                "exam_configuration_id": ec.id,
                "student_id": student_id,
                "blueprint_id": bp.id,
                "status": "GENERATED",
                "total_marks": paper_total or float(bp.total_marks),
                "generated_at": datetime.now(tz=timezone.utc),
                "version_no": 1,
            }
        )
        await self.session.flush()

        # Persist PaperSection + PaperQuestion + AIGenerationLog
        all_pq_dicts: list[dict[str, Any]] = []
        for asm in assembled:
            ps = await self._ps_repo.create(
                {
                    "paper_id": paper.id,
                    "section_label": asm.section_label,
                    "question_type": asm.question_type,
                    "section_marks": asm.section_marks,
                }
            )
            await self.session.flush()

            for seq, sc in enumerate(asm.selected, start=1):
                q_type = sc.candidate.get("question_type", asm.question_type)
                q_id = sc.candidate.get("id", 0)
                pq = await self._pq_repo.create(
                    {
                        "paper_section_id": ps.id,
                        "question_type": q_type,
                        "question_id": q_id,
                        "sequence_no": seq,
                        "marks": sc.candidate.get("marks", 0),
                        "selection_reason_json": sc.as_reason_dict(),
                    }
                )
                all_pq_dicts.append(
                    {
                        "question_type": q_type,
                        "question_id": q_id,
                        "primary_chapter_id": sc.candidate.get("primary_chapter_id"),
                    }
                )

            # AI generation logs (all top-N candidates, selected + not)
            for sc in asm.all_logged_candidates:
                await self._ai_repo.create(
                    {
                        "paper_id": paper.id,
                        "question_type": sc.candidate.get("question_type", asm.question_type),
                        "question_id": sc.candidate.get("id", 0),
                        "blueprint_match_score": sc.blueprint_match_score,
                        "difficulty_match_score": sc.difficulty_match_score,
                        "weak_topic_match_score": sc.weak_topic_match_score,
                        "usage_balance_score": sc.usage_balance_score,
                        "bloom_match_score": sc.bloom_match_score,
                        "final_rank_score": sc.final_rank_score,
                        "selected": any(
                            sel.candidate.get("id") == sc.candidate.get("id")
                            for sel in asm.selected
                        ),
                    }
                )

        # Run validation rules
        section_view = [
            {
                "section_label": asm.section_label,
                "actual_marks": asm.actual_marks,
                "section_marks": asm.section_marks,
                "filled_count": asm.filled_count,
                "required_count": asm.required_count,
                "actual_difficulty_distribution": asm.actual_difficulty_distribution,
                "actual_bloom_distribution": asm.actual_bloom_distribution,
            }
            for asm in assembled
        ]
        results: list[ValidationResult] = run_all_validations(
            paper_total=paper_total or float(bp.total_marks),
            blueprint_total=float(bp.total_marks),
            blueprint_duration=bp.duration_minutes,
            sections=section_view,
            blueprint_sections=bp_sections_dicts,
            paper_questions=all_pq_dicts,
            required_chapter_ids=chapter_ids,
        )

        now = datetime.now(tz=timezone.utc)
        for r in results:
            await self._val_repo.create(
                {
                    "paper_id": paper.id,
                    "rule_code": r.rule_code,
                    "passed": r.passed,
                    "detail": r.detail,
                    "checked_at": now,
                }
            )

        # Update paper status if any validation failed
        if not all_passed(results):
            paper = await self._paper_repo.update(
                paper.id, {"status": "NEEDS_ATTENTION"}
            )

        # Create initial version snapshot
        await self._create_version(
            paper_id=paper.id,
            snapshot=self._paper_snapshot(paper, assembled),
            change_reason="Initial generation",
            changed_by=None,
        )

        await self.session.commit()
        logger.info(
            "Paper generated",
            public_id=str(paper.public_id),
            status=paper.status,
        )
        return self._paper_to_dict(paper)

    # ---------------------------------------------------------------- Review --

    async def approve_paper(
        self,
        public_id: UUID,
        current_user: CurrentUser | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Advance paper from UNDER_REVIEW → APPROVED."""
        paper = await self._paper_repo.get_by_public_id(public_id)
        if paper is None:
            raise NotFoundError(f"Paper {public_id} not found")

        self._assert_transition(paper.status, "APPROVED")

        # Re-validate before approving
        val_rows = await self._val_repo.list_by_paper(paper.id)
        if not all(v.passed for v in val_rows):
            raise BusinessRuleError(
                "Paper has failing validations — resolve before approving"
            )

        updated = await self._paper_repo.update(
            paper.id,
            {
                "status": "APPROVED",
                "approved_at": datetime.now(tz=timezone.utc),
                "approved_by": (
                    current_user.public_id if current_user else None
                ),
            },
        )
        await self.session.commit()
        return self._paper_to_dict(updated)

    # ---------------------------------------------------------------- Versioning --

    async def get_version_history(self, public_id: UUID) -> list[dict[str, Any]]:
        """Return all version entries for a paper, newest first."""
        paper = await self._paper_repo.get_by_public_id(public_id)
        if paper is None:
            raise NotFoundError(f"Paper {public_id} not found")
        versions = await self._pv_repo.list_by_paper(paper.id)
        return [self._version_to_dict(v) for v in versions]

    # ---------------------------------------------------------------- Validations --

    async def get_validations(self, public_id: UUID) -> list[dict[str, Any]]:
        """Return the latest validation results for a paper."""
        paper = await self._paper_repo.get_by_public_id(public_id)
        if paper is None:
            raise NotFoundError(f"Paper {public_id} not found")
        rows = await self._val_repo.list_by_paper(paper.id)
        return [
            {
                "rule_code": r.rule_code,
                "passed": r.passed,
                "detail": r.detail,
            }
            for r in rows
        ]

    # ---------------------------------------------------------------- AI logs --

    async def get_ai_explanation(self, public_id: UUID) -> list[dict[str, Any]]:
        """Return all AI generation log rows (admin/debug only)."""
        paper = await self._paper_repo.get_by_public_id(public_id)
        if paper is None:
            raise NotFoundError(f"Paper {public_id} not found")
        rows = await self._ai_repo.list_by_paper(paper.id)
        return [
            {
                "question_type": r.question_type,
                "question_id": r.question_id,
                "final_rank_score": float(r.final_rank_score),
                "selected": r.selected,
            }
            for r in rows
        ]

    # ---------------------------------------------------------------- Helpers --

    def _build_fetcher(self):
        """
        Returns an async callable satisfying CandidateFetcher protocol.
        Uses QuestionSearchRepository for all candidate queries.
        """

        async def _fetch(
            question_type: str,
            board_id: int,
            class_id: int,
            subject_id: int,
            chapter_ids: list[int],
            difficulty: str,
            bloom_level: str | None,
            exclude_ids: set[tuple[str, int]],
        ) -> list[dict[str, Any]]:
            filters = QuestionSearchFilters(
                board_id=board_id,
                class_id=class_id,
                subject_id=subject_id,
                difficulty=difficulty,
                bloom_level=bloom_level,
                status="ACTIVE",
                page=1,
                page_size=50,
            )
            items, _ = await self._qb_search.search(filters)
            # Filter by question_type and exclude already-selected
            results = []
            for item in items:
                if item.get("question_type") != question_type:
                    continue
                key = (item.get("question_type"), item.get("id"))
                if key in exclude_ids:
                    continue
                results.append(item)
            return results

        return _fetch

    def _assert_transition(self, current: str, target: str) -> None:
        allowed = _PAPER_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise BusinessRuleError(
                f"Cannot transition paper from '{current}' to '{target}'"
            )

    async def _create_version(
        self,
        paper_id: int,
        snapshot: dict[str, Any],
        change_reason: str | None,
        changed_by: Any,
    ) -> PaperVersion:
        await self._pv_repo.mark_all_non_current(paper_id)
        next_no = await self._pv_repo.next_version_no(paper_id)
        return await self._pv_repo.create(
            {
                "paper_id": paper_id,
                "version_no": next_no,
                "snapshot_json": snapshot,
                "change_reason": change_reason,
                "changed_by": changed_by,
                "is_current": True,
            }
        )

    @staticmethod
    def _paper_snapshot(
        paper: Paper,
        assembled: list[AssembledSection],
    ) -> dict[str, Any]:
        """Build a JSON-serializable snapshot of paper state."""
        return {
            "public_id": str(paper.public_id),
            "status": paper.status,
            "total_marks": float(paper.total_marks),
            "sections": [
                {
                    "label": asm.section_label,
                    "question_type": asm.question_type,
                    "section_marks": asm.section_marks,
                    "questions": [
                        {
                            "question_type": sc.candidate.get("question_type"),
                            "question_id": sc.candidate.get("id"),
                            "marks": sc.candidate.get("marks"),
                        }
                        for sc in asm.selected
                    ],
                }
                for asm in assembled
            ],
        }

    @staticmethod
    def _paper_to_dict(paper: Paper) -> dict[str, Any]:
        return {
            "public_id": str(paper.public_id),
            "exam_configuration_id": paper.exam_configuration_id,
            "blueprint_id": paper.blueprint_id,
            "student_id": paper.student_id,
            "status": paper.status,
            "total_marks": float(paper.total_marks),
            "version_no": paper.version_no,
            "generated_at": (
                paper.generated_at.isoformat()
                if paper.generated_at
                else None
            ),
            "approved_at": (
                paper.approved_at.isoformat()
                if paper.approved_at
                else None
            ),
            "created_at": paper.created_at.isoformat(),
            "updated_at": paper.updated_at.isoformat(),
        }

    @staticmethod
    def _version_to_dict(v: PaperVersion) -> dict[str, Any]:
        return {
            "public_id": str(v.public_id),
            "paper_id": v.paper_id,
            "version_no": v.version_no,
            "snapshot_json": v.snapshot_json,
            "change_reason": v.change_reason,
            "is_current": v.is_current,
            "created_at": v.created_at.isoformat(),
        }

    @staticmethod
    def _sec_to_dict(sec) -> dict[str, Any]:
        return {
            "section_label": sec.section_label,
            "question_type": sec.question_type,
            "section_marks": float(sec.section_marks),
            "question_count": sec.question_count,
            "difficulty_distribution_json": sec.difficulty_distribution_json or {},
            "bloom_distribution_json": sec.bloom_distribution_json,
            "chapter_scope_json": sec.chapter_scope_json,
        }
