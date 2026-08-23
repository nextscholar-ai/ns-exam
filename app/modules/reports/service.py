"""
Reporting Engine module — Service layer (Phase 16 §5.5).

Contains `ReportService`:
  1. `generate_student_report_card`: Compiles comprehensive student progress snapshot.
  2. `generate_exam_analysis_report`: Compiles exam analysis document.
  3. `publish_report`: Transitions snapshot GENERATED → PUBLISHED.
  4. `export_report_text`: Formats report data into human-readable text/markdown (PDF simulation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.security.rbac import CurrentUser
from app.modules.analytics.service import AnalyticsService
from app.modules.learning_profile.service import LearningProfileService
from app.modules.reports.events import ReportGenerated, publish_report_generated
from app.modules.reports.repository import ReportSnapshotRepository

logger = get_logger(__name__)


class ReportService:
    """Service orchestrating report card & exam report snapshot generation and publishing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.report_repo = ReportSnapshotRepository(session)
        self.analytics_service = AnalyticsService(session)
        self.profile_service = LearningProfileService(session)

    async def generate_student_report_card(
        self,
        student_id: int,
        subject_id: int,
        title: str | None = None,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Generate and persist a `STUDENT_PROGRESS` report snapshot.
        """
        # Fetch analytics dashboard
        dash = await self.analytics_service.get_student_dashboard(student_id, subject_id)
        profile = await self.profile_service.get_learning_profile(student_id, subject_id=subject_id)

        report_title = title or f"Student Progress Report Card - Student #{student_id}"

        # Build summary text
        summary = (
            f"Progress Report for Student #{student_id}:\n"
            f"Overall Mastery: {dash['overall_mastery'] * 100:.1f}%\n"
            f"Average Score: {dash['average_percentage']:.1f}%\n"
            f"Exams Taken: {dash['total_exams_taken']}"
            f" (Passed: {dash['passed_exams_count']},"
            f" Failed: {dash['failed_exams_count']})\n"
            f"Performance Trend: {dash['trend_direction']}\n"
            f"At Risk Status: {'YES' if dash['is_at_risk'] else 'NO'}\n"
            f"Weak Topics Count: {len(profile['weak_topic_ids'])}\n"
            f"Strong Topics Count: {len(profile['strong_topic_ids'])}\n"
        )

        report_data = {
            "dashboard": dash,
            "profile": profile,
        }

        generated_by = current_user.public_id if current_user else "SYSTEM"

        snapshot = await self.report_repo.create(
            {
                "report_type": "STUDENT_PROGRESS",
                "status": "GENERATED",
                "student_id": student_id,
                "title": report_title,
                "summary_text": summary,
                "report_data_json": report_data,
                "generated_by": generated_by,
            }
        )

        await self.session.commit()

        logger.info(
            "reports.student_report_generated",
            public_id=str(snapshot.public_id),
            student_id=student_id,
        )

        await publish_report_generated(
            ReportGenerated(
                report_public_id=str(snapshot.public_id),
                report_type="STUDENT_PROGRESS",
                student_id=student_id,
                exam_id=None,
            )
        )

        return self._report_to_dict(snapshot)

    async def generate_exam_analysis_report(
        self,
        exam_id: int,
        class_id: int,
        subject_id: int,
        title: str | None = None,
        current_user: CurrentUser | None = None,
    ) -> dict[str, Any]:
        """
        Generate and persist an `EXAM_ANALYSIS` report snapshot.
        """
        class_analytics = await self.analytics_service.get_class_analytics(
            class_id=class_id, exam_id=exam_id, subject_id=subject_id
        )

        report_title = title or f"Exam Performance Analysis Report - Exam #{exam_id}"

        summary = (
            f"Exam Analysis for Exam #{exam_id} (Class #{class_id}):\n"
            f"Appeared Students: {class_analytics['appeared_students_count']}\n"
            f"Pass Rate: {class_analytics['pass_percentage']}%\n"
            f"Class Average: {class_analytics['class_average_score']}\n"
            f"Highest Score: {class_analytics['highest_score']}"
            f" / Lowest: {class_analytics['lowest_score']}\n"
        )

        generated_by = current_user.public_id if current_user else "SYSTEM"

        snapshot = await self.report_repo.create(
            {
                "report_type": "EXAM_ANALYSIS",
                "status": "GENERATED",
                "class_id": class_id,
                "exam_id": exam_id,
                "title": report_title,
                "summary_text": summary,
                "report_data_json": class_analytics,
                "generated_by": generated_by,
            }
        )

        await self.session.commit()

        logger.info(
            "reports.exam_report_generated",
            public_id=str(snapshot.public_id),
            exam_id=exam_id,
        )

        await publish_report_generated(
            ReportGenerated(
                report_public_id=str(snapshot.public_id),
                report_type="EXAM_ANALYSIS",
                student_id=None,
                exam_id=exam_id,
            )
        )

        return self._report_to_dict(snapshot)

    async def publish_report(self, public_id: UUID | str) -> dict[str, Any]:
        """Publish a generated report snapshot (GENERATED → PUBLISHED)."""
        snapshot = await self.report_repo.get_by(public_id=str(public_id))
        if snapshot is None:
            raise NotFoundError(f"ReportSnapshot {public_id} not found")

        snapshot.published_at = datetime.now(tz=timezone.utc)
        await self.report_repo.transition_status(snapshot.id, "PUBLISHED")
        await self.session.commit()
        return self._report_to_dict(snapshot)

    async def get_report_by_public_id(self, public_id: UUID | str) -> dict[str, Any]:
        """Fetch a report snapshot by public_id."""
        snapshot = await self.report_repo.get_by(public_id=str(public_id))
        if snapshot is None:
            raise NotFoundError(f"ReportSnapshot {public_id} not found")
        return self._report_to_dict(snapshot)

    @staticmethod
    def _report_to_dict(r: Any) -> dict[str, Any]:
        return {
            "public_id": str(r.public_id),
            "report_type": r.report_type,
            "status": r.status,
            "student_id": r.student_id,
            "class_id": r.class_id,
            "exam_id": r.exam_id,
            "title": r.title,
            "summary_text": r.summary_text,
            "report_data_json": r.report_data_json,
            "generated_by": r.generated_by,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "created_at": r.created_at.isoformat(),
        }
