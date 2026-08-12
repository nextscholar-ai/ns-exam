"""
Recommendation Engine module — ORM models (Phase 15 §6).

Tables owned here:
  practice_recommendations  — aggregate root storing recommended practice sets / mock exams (§6.1).
  recommendation_items      — question/topic items inside a recommendation (§6.2).
  recommendation_feedbacks  — student/teacher feedback on recommendation quality (§6.3).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db.base_model import Base, BaseMixin

_JSON = JSONB().with_variant(JSON(), "sqlite")


class PracticeRecommendation(BaseMixin, Base):
    """
    Practice Recommendation Aggregate Root (Phase 15 §6.1).

    Tracks personalized practice sets and mock exam recommendations generated
    from Phase 14 Mastery Engine data (weak topics).
    """

    __tablename__ = "practice_recommendations"
    __table_args__ = (
        Index("ix_pr_student_id", "student_id"),
        Index("ix_pr_status", "status"),
        Index("ix_pr_recommendation_type", "recommendation_type"),
    )

    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PRACTICE_SET"
    )  # PRACTICE_SET | PERSONALIZED_MOCK | REVISION_FLASHCARDS
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="RECOMMENDED"
    )  # RECOMMENDED | ACCEPTED | IN_PROGRESS | COMPLETED | DISMISSED | EXPIRED
    target_topic_ids_json: Mapped[list] = mapped_column(_JSON, nullable=False)
    recommended_difficulty: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )  # EASY | MEDIUM | HARD | ADAPTIVE
    priority_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.5
    )  # 0.0000 – 1.0000
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    generated_paper_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items: Mapped[list["RecommendationItem"]] = relationship(
        back_populates="recommendation",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    feedbacks: Mapped[list["RecommendationFeedback"]] = relationship(
        back_populates="recommendation",
        lazy="raise",
        cascade="all, delete-orphan",
    )


class RecommendationItem(BaseMixin, Base):
    """
    Individual item inside a recommendation (§6.2).

    Represents a specific question or topic recommended for practice.
    """

    __tablename__ = "recommendation_items"
    __table_args__ = (
        Index("ix_ri_recommendation_id", "recommendation_id"),
        Index("ix_ri_topic_id", "topic_id"),
    )

    recommendation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_recommendations.id"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chapters.id"), nullable=False
    )
    question_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OBJECTIVE"
    )  # OBJECTIVE | SUBJECTIVE | FILL_BLANK
    question_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reason_json: Mapped[dict | None] = mapped_column(_JSON, nullable=True)

    recommendation: Mapped["PracticeRecommendation"] = relationship(
        back_populates="items",
        lazy="raise",
    )


class RecommendationFeedback(BaseMixin, Base):
    """
    Student or Teacher feedback on recommendation quality (§6.3).
    """

    __tablename__ = "recommendation_feedbacks"
    __table_args__ = (
        Index("ix_rf_recommendation_id", "recommendation_id"),
    )

    recommendation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_recommendations.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    rating: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # HELPFUL | TOO_EASY | TOO_HARD | NOT_RELEVANT
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommendation: Mapped["PracticeRecommendation"] = relationship(
        back_populates="feedbacks",
        lazy="raise",
    )
