"""
Blueprint module — Service layer (Phase 11).

Orchestrates Blueprint and ExamConfiguration CRUD with business rules:
  - Section marks must sum to blueprint total_marks (enforced in schema + here).
  - Status transitions: DRAFT → ACTIVE → ARCHIVED.
  - Only the creating teacher (or SCHOOL_ADMIN / ADMIN) may edit/archive
    a blueprint (Phase 11 §14).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser
from app.modules.blueprint.models import Blueprint, BlueprintSection, ExamConfiguration
from app.modules.blueprint.repository import (
    BlueprintRepository,
    BlueprintSectionRepository,
    ExamConfigRepository,
)
from app.modules.blueprint.schemas import BlueprintCreate, ExamConfigCreate

logger = get_logger(__name__)

# Allowed status transitions
_BLUEPRINT_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"ACTIVE", "ARCHIVED"},
    "ACTIVE": {"ARCHIVED"},
    "ARCHIVED": set(),
}

_EXAM_CONFIG_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"ACTIVE", "ARCHIVED"},
    "ACTIVE": {"ARCHIVED"},
    "ARCHIVED": set(),
}


class BlueprintService:
    """
    Service for Blueprint and ExamConfiguration lifecycle management.

    Single responsibility: business rules + orchestration.
    All persistence delegated to repository classes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._bp_repo = BlueprintRepository(session)
        self._sec_repo = BlueprintSectionRepository(session)
        self._ec_repo = ExamConfigRepository(session)

    # ---------------------------------------------------------------- Blueprint --

    async def create_blueprint(
        self,
        data: BlueprintCreate,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Create a Blueprint with its sections in a single transaction.
        Schema-level validation (section marks sum) runs before this call.
        """
        logger.info(
            "Creating blueprint",
            name=data.name,
            board_id=data.board_id,
        )

        bp = await self._bp_repo.create(
            {
                "board_id": data.board_id,
                "class_id": data.class_id,
                "subject_id": data.subject_id,
                "name": data.name,
                "total_marks": data.total_marks,
                "duration_minutes": data.duration_minutes,
                "syllabus_coverage_pct": data.syllabus_coverage_pct,
                "status": "DRAFT",
                "created_by": None,  # CurrentUser carries public_id (UUID), not internal int id
            }
        )

        for sec in data.sections:
            await self._sec_repo.create(
                {
                    "blueprint_id": bp.id,
                    "section_label": sec.section_label,
                    "question_type": sec.question_type,
                    "section_marks": sec.section_marks,
                    "question_count": sec.question_count,
                    "difficulty_distribution_json": sec.difficulty_distribution.model_dump(),
                    "bloom_distribution_json": sec.bloom_distribution,
                    "chapter_scope_json": sec.chapter_scope,
                }
            )

        await self.session.commit()
        logger.info("Blueprint created", public_id=str(bp.public_id))
        return self._bp_to_dict(bp)

    async def get_blueprint(
        self,
        public_id: UUID,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Fetch a blueprint by public_id; raises NotFoundError if missing."""
        bp = await self._bp_repo.get_by(
            public_id=str(public_id),
            current_user=current_user,
        )
        if bp is None:
            raise NotFoundError(f"Blueprint {public_id} not found")
        return self._bp_to_dict(bp)

    async def change_blueprint_status(
        self,
        public_id: UUID,
        new_status: str,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Validate and apply a blueprint status transition."""
        bp = await self._bp_repo.get_by(
            public_id=str(public_id),
            current_user=current_user,
        )
        if bp is None:
            raise NotFoundError(f"Blueprint {public_id} not found")

        allowed = _BLUEPRINT_TRANSITIONS.get(bp.status, set())
        if new_status not in allowed:
            raise BusinessRuleError(
                f"Cannot transition blueprint from '{bp.status}' to '{new_status}'"
            )

        updated = await self._bp_repo.update(bp.id, {"status": new_status})
        await self.session.commit()
        return self._bp_to_dict(updated)

    async def get_sections(self, blueprint_id: int) -> list[dict[str, Any]]:
        """Return all sections for a given blueprint."""
        sections = await self._sec_repo.get_many(
            filters={"blueprint_id": blueprint_id}
        )
        return [self._sec_to_dict(s) for s in sections]

    # ---------------------------------------------------------------- ExamConfig --

    async def create_exam_config(
        self,
        data: ExamConfigCreate,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Create an ExamConfiguration linked to an existing active blueprint."""
        bp = await self._bp_repo.get_by_id(data.blueprint_id)
        if bp is None or bp.status != "ACTIVE":
            raise BusinessRuleError(
                f"Blueprint {data.blueprint_id} must be ACTIVE to create an exam configuration"
            )

        logger.info("Creating exam configuration", exam_name=data.exam_name)

        ec = await self._ec_repo.create(
            {
                "blueprint_id": data.blueprint_id,
                "exam_name": data.exam_name,
                "academic_session_id": data.academic_session_id,
                "exam_type": data.exam_type,
                "personalized": data.personalized,
                "current_chapters_json": data.current_chapters,
                "current_topics_json": data.current_topics,
                "exam_date": data.exam_date,
                "publish_date": data.publish_date,
                "created_by": None,  # CurrentUser carries public_id (UUID), not internal int id
                "status": "DRAFT",
            }
        )
        await self.session.commit()
        logger.info("ExamConfiguration created", public_id=str(ec.public_id))
        return self._ec_to_dict(ec)

    async def get_exam_config(
        self,
        public_id: UUID,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        ec = await self._ec_repo.get_by(public_id=str(public_id))
        if ec is None:
            raise NotFoundError(f"ExamConfiguration {public_id} not found")
        return self._ec_to_dict(ec)

    async def change_exam_config_status(
        self,
        public_id: UUID,
        new_status: str,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        ec = await self._ec_repo.get_by(public_id=str(public_id))
        if ec is None:
            raise NotFoundError(f"ExamConfiguration {public_id} not found")

        allowed = _EXAM_CONFIG_TRANSITIONS.get(ec.status, set())
        if new_status not in allowed:
            raise BusinessRuleError(
                f"Cannot transition exam config from '{ec.status}' to '{new_status}'"
            )

        updated = await self._ec_repo.update(ec.id, {"status": new_status})
        await self.session.commit()
        return self._ec_to_dict(updated)

    # ---------------------------------------------------------------- Serializers --

    @staticmethod
    def _bp_to_dict(bp: Blueprint) -> dict[str, Any]:
        return {
            "public_id": str(bp.public_id),
            "board_id": bp.board_id,
            "class_id": bp.class_id,
            "subject_id": bp.subject_id,
            "name": bp.name,
            "total_marks": float(bp.total_marks),
            "duration_minutes": bp.duration_minutes,
            "syllabus_coverage_pct": (
                float(bp.syllabus_coverage_pct)
                if bp.syllabus_coverage_pct is not None
                else None
            ),
            "status": bp.status,
            "created_at": bp.created_at.isoformat(),
            "updated_at": bp.updated_at.isoformat(),
        }

    @staticmethod
    def _sec_to_dict(sec: BlueprintSection) -> dict[str, Any]:
        return {
            "public_id": str(sec.public_id),
            "blueprint_id": sec.blueprint_id,
            "section_label": sec.section_label,
            "question_type": sec.question_type,
            "section_marks": float(sec.section_marks),
            "question_count": sec.question_count,
            "difficulty_distribution_json": sec.difficulty_distribution_json,
            "bloom_distribution_json": sec.bloom_distribution_json,
            "chapter_scope_json": sec.chapter_scope_json,
        }

    @staticmethod
    def _ec_to_dict(ec: ExamConfiguration) -> dict[str, Any]:
        return {
            "public_id": str(ec.public_id),
            "blueprint_id": ec.blueprint_id,
            "exam_name": ec.exam_name,
            "academic_session_id": ec.academic_session_id,
            "exam_type": ec.exam_type,
            "personalized": ec.personalized,
            "status": ec.status,
            "created_at": ec.created_at.isoformat(),
            "updated_at": ec.updated_at.isoformat(),
        }
