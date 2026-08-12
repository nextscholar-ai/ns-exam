"""
Recommendation Engine module — Repository layer (Phase 15 §8).

Provides specialized repositories:
  - PracticeRecommendationRepository
  - RecommendationItemRepository
  - RecommendationFeedbackRepository
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.recommendation.domain.state_machine import validate_recommendation_transition
from app.modules.recommendation.models import (
    PracticeRecommendation,
    RecommendationFeedback,
    RecommendationItem,
)


class PracticeRecommendationRepository(BaseRepository[PracticeRecommendation]):
    """Repository for PracticeRecommendation aggregate root."""

    ALLOWED_SORT_FIELDS = {
        "created_at": PracticeRecommendation.created_at,
        "priority_score": PracticeRecommendation.priority_score,
        "status": PracticeRecommendation.status,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PracticeRecommendation)

    async def list_by_student(
        self, student_id: int, status: str | None = None
    ) -> list[PracticeRecommendation]:
        stmt = (
            select(PracticeRecommendation)
            .where(PracticeRecommendation.student_id == student_id)
            .where(PracticeRecommendation.is_deleted == False)  # noqa: E712
        )
        if status is not None:
            stmt = stmt.where(PracticeRecommendation.status == status)
        stmt = stmt.order_by(PracticeRecommendation.created_at.desc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def transition_status(
        self, recommendation_id: int, target_status: str
    ) -> PracticeRecommendation:
        """
        State machine status transition enforcement.
        Validates transition via state_machine.py.
        """
        rec = await self.get_or_raise(recommendation_id)
        validate_recommendation_transition(rec.status, target_status)
        rec.status = target_status
        await self.session.flush()
        return rec


class RecommendationItemRepository(BaseRepository[RecommendationItem]):
    """Repository for recommendation items."""

    ALLOWED_SORT_FIELDS = {"sequence_no": RecommendationItem.sequence_no}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecommendationItem)

    async def list_by_recommendation(
        self, recommendation_id: int
    ) -> list[RecommendationItem]:
        stmt = (
            select(RecommendationItem)
            .where(RecommendationItem.recommendation_id == recommendation_id)
            .where(RecommendationItem.is_deleted == False)  # noqa: E712
            .order_by(RecommendationItem.sequence_no.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class RecommendationFeedbackRepository(BaseRepository[RecommendationFeedback]):
    """Repository for recommendation feedback entries."""

    ALLOWED_SORT_FIELDS = {"created_at": RecommendationFeedback.created_at}

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecommendationFeedback)

    async def list_by_recommendation(
        self, recommendation_id: int
    ) -> list[RecommendationFeedback]:
        stmt = (
            select(RecommendationFeedback)
            .where(RecommendationFeedback.recommendation_id == recommendation_id)
            .where(RecommendationFeedback.is_deleted == False)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
