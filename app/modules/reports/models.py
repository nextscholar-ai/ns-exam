"""
Reporting Engine module — ORM models (Phase 16 §6.5).

Table owned here:
  report_snapshots — immutable exported report snapshots (§6.5).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db.base_model import Base, BaseMixin

_JSON = JSONB().with_variant(JSON(), "sqlite")


class ReportSnapshot(BaseMixin, Base):
    """
    Exported report snapshot (Phase 16 §6.5).

    Stores generated student report cards, class performance reports,
    and exam analysis documents with JSON payload and text/markdown summary.
    """

    __tablename__ = "report_snapshots"
    __table_args__ = (
        Index("ix_rs_report_type", "report_type"),
        Index("ix_rs_student_id", "student_id"),
        Index("ix_rs_exam_id", "exam_id"),
        Index("ix_rs_status", "status"),
    )

    report_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # STUDENT_PROGRESS | EXAM_ANALYSIS | CLASS_PERFORMANCE
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="GENERATED"
    )  # GENERATED | PUBLISHED | ARCHIVED
    student_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=True
    )
    class_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("classes.id"), nullable=True
    )
    exam_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("exams.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_data_json: Mapped[dict] = mapped_column(_JSON, nullable=False)
    generated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
