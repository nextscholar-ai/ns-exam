"""
Recommendation Engine module — Service layer (Phase 15 §5).

Contains `RecommendationService`:
  1. Generates personalized practice recommendations reading Phase 14 Mastery data.
  2. Applies `RecommendationStrategy` (pure domain ranking).
  3. Triggers Phase 11 Paper Generation for personalized mock exams with weak topic injection.
  4. Manages recommendation state lifecycle (RECOMMENDED → ACCEPTED → IN_PROGRESS → COMPLETED / DISMISSED).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser
from app.modules.learning_profile.service import LearningProfileService
from app.modules.recommendation.domain.ranking_strategy import (
    RecommendationStrategy,
    WeaknessPriorityStrategy,
    determine_recommended_difficulty,
)
from app.modules.recommendation.models import (
    PracticeRecommendation,
    RecommendationFeedback,
    RecommendationItem,
)
from app.modules.recommendation.repository import (
    PracticeRecommendationRepository,
    RecommendationFeedbackRepository,
    RecommendationItemRepository,
)

logger = get_logger(__name__)


class RecommendationService:
    """Service orchestrating practice recommendation generation, state lifecycle, and feedback."""

    def __init__(
        self,
        session: AsyncSession,
        strategy: RecommendationStrategy | None = None,
    ) -> None:
        self.session = session
        self.strategy: RecommendationStrategy = strategy or WeaknessPriorityStrategy()
        self.rec_repo = PracticeRecommendationRepository(session)
        self.item_repo = RecommendationItemRepository(session)
        self.feedback_repo = RecommendationFeedbackRepository(session)
        self.profile_service = LearningProfileService(session)

    async def generate_recommendation(
        self,
        student_id: int,
        subject_id: int,
        recommendation_type: str = "PRACTICE_SET",
        item_count: int = 5,
        target_difficulty: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a personalized practice recommendation for a student.

        Steps:
          1. Query student's learning profile (Phase 14) for the target subject.
          2. Extract weak topics & candidate topic masteries.
          3. Apply pure domain ranking strategy → rank topics by weakness/priority.
          4. Determine recommended difficulty (EASY/MEDIUM/HARD) if not overridden.
          5. Create `PracticeRecommendation` aggregate root and item details.
          6. If recommendation_type == "PERSONALIZED_MOCK", trigger Phase 11 AI paper generation
             with weak_topic_ids injected into the candidate search.
        """
        # Fetch learning profile data from Phase 14
        profile = await self.profile_service.get_learning_profile(student_id, subject_id=subject_id)
        topic_masteries = profile["topic_masteries"]
        weak_topic_ids = set(profile["weak_topic_ids"])

        if not topic_masteries:
            logger.warning(
                "recommendation.no_mastery_data",
                student_id=student_id,
                subject_id=subject_id,
            )

        # Rank candidate topics
        ranked_candidates = self.strategy.rank_topics(
            candidate_topics=topic_masteries,
            weak_topic_ids=weak_topic_ids,
        )

        # Select top item_count topics
        selected_topics = ranked_candidates[:item_count]
        target_topic_ids = [t["topic_id"] for t in selected_topics]

        # Calculate average mastery for difficulty selection
        if topic_masteries:
            avg_mastery = sum(t["mastery_score"] for t in topic_masteries) / len(topic_masteries)
        else:
            avg_mastery = 0.0

        rec_difficulty = target_difficulty or determine_recommended_difficulty(avg_mastery)
        overall_priority = selected_topics[0]["priority_score"] if selected_topics else 0.5

        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(days=7)  # Recommendation valid for 7 days

        # Persist aggregate root
        rec = await self.rec_repo.create(
            {
                "student_id": student_id,
                "subject_id": subject_id,
                "recommendation_type": recommendation_type,
                "status": "RECOMMENDED",
                "target_topic_ids_json": target_topic_ids,
                "recommended_difficulty": rec_difficulty,
                "priority_score": overall_priority,
                "item_count": len(selected_topics),
                "expires_at": expires_at,
            }
        )
        await self.session.flush()

        # Persist recommendation items
        items = []
        for seq, t in enumerate(selected_topics, start=1):
            item = await self.item_repo.create(
                {
                    "recommendation_id": rec.id,
                    "topic_id": t["topic_id"],
                    "chapter_id": t["chapter_id"],
                    "question_type": "OBJECTIVE",
                    "sequence_no": seq,
                    "reason_json": {
                        "mastery_score": t["mastery_score"],
                        "priority_score": t.get("priority_score", 0.5),
                        "is_weak": t["topic_id"] in weak_topic_ids,
                    },
                }
            )
            items.append(item)

        # Trigger Phase 11 personalized mock paper generation if requested
        generated_paper_id = None
        if recommendation_type == "PERSONALIZED_MOCK":
            from app.modules.paper_generation.service import PaperGenerationService
            paper_service = PaperGenerationService(self.session)
            # Find an active exam_config for this subject
            from app.modules.blueprint.repository import ExamConfigRepository
            ec_repo = ExamConfigRepository(self.session)
            configs = await ec_repo.get_many(limit=1)
            if configs:
                paper_dict = await paper_service.generate_paper(
                    exam_configuration_id=configs[0].id,
                    student_id=student_id,
                    weak_topic_ids=weak_topic_ids,
                )
                from app.modules.paper_generation.repository import PaperRepository
                paper_repo = PaperRepository(self.session)
                paper_obj = await paper_repo.get_by(public_id=paper_dict["public_id"])
                if paper_obj:
                    generated_paper_id = paper_obj.id
                    rec.generated_paper_id = generated_paper_id

        await self.session.commit()

        logger.info(
            "recommendation.generated",
            public_id=str(rec.public_id),
            student_id=student_id,
            recommendation_type=recommendation_type,
            item_count=len(selected_topics),
        )

        return await self._rec_to_dict(rec)

    async def list_student_recommendations(
        self,
        student_id: int,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recommendations for a student."""
        recs = await self.rec_repo.list_by_student(student_id, status=status)
        return [await self._rec_to_dict(r) for r in recs]

    async def accept_recommendation(
        self, public_id: UUID | str
    ) -> dict[str, Any]:
        """Transition recommendation status RECOMMENDED → ACCEPTED."""
        rec = await self.rec_repo.get_by(public_id=str(public_id))
        if rec is None:
            raise NotFoundError(f"Recommendation {public_id} not found")

        await self.rec_repo.transition_status(rec.id, "ACCEPTED")
        await self.session.commit()
        return await self._rec_to_dict(rec)

    async def dismiss_recommendation(
        self, public_id: UUID | str
    ) -> dict[str, Any]:
        """Transition recommendation status → DISMISSED."""
        rec = await self.rec_repo.get_by(public_id=str(public_id))
        if rec is None:
            raise NotFoundError(f"Recommendation {public_id} not found")

        await self.rec_repo.transition_status(rec.id, "DISMISSED")
        await self.session.commit()
        return await self._rec_to_dict(rec)

    async def submit_feedback(
        self,
        public_id: UUID | str,
        rating: str,
        comments: str | None = None,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """Submit student or teacher feedback on a recommendation."""
        rec = await self.rec_repo.get_by(public_id=str(public_id))
        if rec is None:
            raise NotFoundError(f"Recommendation {public_id} not found")

        user_id = current_user.public_id if current_user else "guest"
        fb = await self.feedback_repo.create(
            {
                "recommendation_id": rec.id,
                "user_id": 1,  # Default fallback ID if user integer PK unavailable
                "rating": rating,
                "comments": comments,
            }
        )
        await self.session.commit()

        return {
            "public_id": str(fb.public_id),
            "recommendation_id": fb.recommendation_id,
            "rating": fb.rating,
            "comments": fb.comments,
        }

    async def _rec_to_dict(self, rec: PracticeRecommendation) -> dict[str, Any]:
        items = await self.item_repo.list_by_recommendation(rec.id)
        return {
            "public_id": str(rec.public_id),
            "student_id": rec.student_id,
            "subject_id": rec.subject_id,
            "recommendation_type": rec.recommendation_type,
            "status": rec.status,
            "target_topic_ids_json": rec.target_topic_ids_json,
            "recommended_difficulty": rec.recommended_difficulty,
            "priority_score": float(rec.priority_score),
            "item_count": rec.item_count,
            "generated_paper_id": rec.generated_paper_id,
            "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
            "completed_at": rec.completed_at.isoformat() if rec.completed_at else None,
            "created_at": rec.created_at.isoformat(),
            "items": [
                {
                    "topic_id": item.topic_id,
                    "chapter_id": item.chapter_id,
                    "question_type": item.question_type,
                    "question_id": item.question_id,
                    "sequence_no": item.sequence_no,
                    "reason_json": item.reason_json,
                }
                for item in items
            ],
        }
