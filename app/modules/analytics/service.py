"""
Analytics Engine module — Service layer (Phase 16 §5).

Contains `AnalyticsService`:
  1. `get_student_dashboard`: Computes or returns cached student performance metrics,
     overall mastery, trend direction (IMPROVING/STABLE/DECLINING), and risk status.
  2. `get_class_analytics`: Computes class average, pass percentage, top weak topics,
     and count of at-risk students for an exam.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.modules.analytics.domain.calculators import (
    compute_pass_percentage,
    compute_trend_direction,
    evaluate_student_risk,
)
from app.modules.analytics.events import AnalyticsUpdated, publish_analytics_updated
from app.modules.analytics.repository import (
    ClassAnalyticsSummaryRepository,
    StudentAnalyticsSummaryRepository,
)
from app.modules.evaluation.repository import EvaluationRepository
from app.modules.exam_management.repository import StudentAttemptRepository
from app.modules.learning_profile.service import LearningProfileService

logger = get_logger(__name__)


class AnalyticsService:
    """Service orchestrating student & class performance analytics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sas_repo = StudentAnalyticsSummaryRepository(session)
        self.cas_repo = ClassAnalyticsSummaryRepository(session)
        self.profile_service = LearningProfileService(session)
        self.attempt_repo = StudentAttemptRepository(session)
        self.eval_repo = EvaluationRepository(session)

    async def get_student_subject_ids(self, student_id: int) -> list[int]:
        """Distinct subject IDs the student has attempted (used by the nightly
        recompute job to refresh every subject dashboard)."""
        return await self.attempt_repo.list_subject_ids_by_student(student_id)

    async def get_student_dashboard(
        self,
        student_id: int,
        subject_id: int,
    ) -> dict[str, Any]:
        """
        Compute & return student performance analytics dashboard.

        Metrics calculated:
          - Total attempts, passed vs failed counts, avg percentage.
          - Overall subject mastery (from Phase 14).
          - Weak and strong topic IDs (from Phase 14).
          - Trend direction (IMPROVING / DECLINING / STABLE) from history.
          - Risk evaluation: marks student as at-risk if mastery < 40% or failed >= 2 exams.
        """
        # Fetch learning profile from Phase 14
        profile = await self.profile_service.get_learning_profile(student_id, subject_id=subject_id)
        topic_masteries = profile["topic_masteries"]
        subject_masteries = profile["subject_masteries"]

        overall_mastery = subject_masteries[0]["mastery_score"] if subject_masteries else 0.0

        # Fetch all student attempts for this student
        attempts = await self.attempt_repo.get_many(filters={"student_id": student_id})
        total_exams = len(attempts)

        passed_count = 0
        failed_count = 0
        percentages: list[float] = []

        for att in attempts:
            eval_obj = await self.eval_repo.get_by_attempt(att.id)
            if eval_obj and eval_obj.status in ("COMPLETED", "LOCKED", "PUBLISHED"):
                pct = float(eval_obj.percentage or 0.0)
                percentages.append(pct)
                if eval_obj.result_status == "PASS":
                    passed_count += 1
                else:
                    failed_count += 1

        avg_pct = round(sum(percentages) / len(percentages), 2) if percentages else 0.0

        # Calculate mastery trend direction from history if available
        trend_scores = [t["mastery_score"] for t in topic_masteries]
        trend_direction = compute_trend_direction(trend_scores)

        # Evaluate at-risk status
        is_at_risk, risk_reasons = evaluate_student_risk(
            overall_mastery=overall_mastery,
            failed_exams_count=failed_count,
            trend_direction=trend_direction,
        )

        now = datetime.now(tz=timezone.utc)

        # Upsert cached summary row
        sas = await self.sas_repo.get_by_student_subject(student_id, subject_id)
        if sas:
            sas.total_exams_taken = total_exams
            sas.passed_exams_count = passed_count
            sas.failed_exams_count = failed_count
            sas.average_percentage = avg_pct
            sas.overall_mastery = overall_mastery
            sas.trend_direction = trend_direction
            sas.is_at_risk = is_at_risk
            sas.risk_reasons_json = risk_reasons
            sas.last_computed_at = now
        else:
            sas = await self.sas_repo.create(
                {
                    "student_id": student_id,
                    "subject_id": subject_id,
                    "total_exams_taken": total_exams,
                    "passed_exams_count": passed_count,
                    "failed_exams_count": failed_count,
                    "average_percentage": avg_pct,
                    "overall_mastery": overall_mastery,
                    "trend_direction": trend_direction,
                    "is_at_risk": is_at_risk,
                    "risk_reasons_json": risk_reasons,
                    "last_computed_at": now,
                }
            )

        await self.session.commit()

        logger.info(
            "analytics.student_dashboard_computed",
            student_id=student_id,
            subject_id=subject_id,
            is_at_risk=is_at_risk,
        )

        await publish_analytics_updated(
            AnalyticsUpdated(
                student_id=student_id,
                class_id=None,
                is_at_risk=is_at_risk,
            )
        )

        return {
            "student_id": student_id,
            "subject_id": subject_id,
            "total_exams_taken": total_exams,
            "passed_exams_count": passed_count,
            "failed_exams_count": failed_count,
            "average_percentage": avg_pct,
            "overall_mastery": overall_mastery,
            "trend_direction": trend_direction,
            "is_at_risk": is_at_risk,
            "risk_reasons": risk_reasons,
            "weak_topic_ids": profile["weak_topic_ids"],
            "strong_topic_ids": profile["strong_topic_ids"],
            "last_computed_at": now.isoformat(),
        }

    async def get_class_analytics(
        self,
        class_id: int,
        exam_id: int,
        subject_id: int,
    ) -> dict[str, Any]:
        """
        Compute & return class-level exam performance analytics.
        """
        attempts = await self.attempt_repo.get_many(filters={"exam_id": exam_id})
        appeared_count = len(attempts)

        passed_count = 0
        scores: list[float] = []

        for att in attempts:
            eval_obj = await self.eval_repo.get_by_attempt(att.id)
            if eval_obj and eval_obj.status in ("COMPLETED", "LOCKED", "PUBLISHED"):
                tot = float(eval_obj.total_marks or 0.0)
                scores.append(tot)
                if eval_obj.result_status == "PASS":
                    passed_count += 1

        pass_pct = compute_pass_percentage(passed_count, appeared_count)
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        high_score = max(scores) if scores else 0.0
        low_score = min(scores) if scores else 0.0

        now = datetime.now(tz=timezone.utc)

        cas = await self.cas_repo.get_by_class_exam(class_id, exam_id)
        if cas:
            cas.appeared_students_count = appeared_count
            cas.passed_students_count = passed_count
            cas.pass_percentage = pass_pct
            cas.class_average_score = avg_score
            cas.highest_score = high_score
            cas.lowest_score = low_score
            cas.last_computed_at = now
        else:
            cas = await self.cas_repo.create(
                {
                    "class_id": class_id,
                    "exam_id": exam_id,
                    "subject_id": subject_id,
                    "total_students_count": appeared_count,
                    "appeared_students_count": appeared_count,
                    "passed_students_count": passed_count,
                    "pass_percentage": pass_pct,
                    "class_average_score": avg_score,
                    "highest_score": high_score,
                    "lowest_score": low_score,
                    "at_risk_students_count": 0,
                    "last_computed_at": now,
                }
            )

        await self.session.commit()

        return {
            "class_id": class_id,
            "exam_id": exam_id,
            "subject_id": subject_id,
            "total_students_count": appeared_count,
            "appeared_students_count": appeared_count,
            "passed_students_count": passed_count,
            "pass_percentage": pass_pct,
            "class_average_score": avg_score,
            "highest_score": high_score,
            "lowest_score": low_score,
            "at_risk_students_count": 0,
            "top_weak_topic_ids": [],
            "last_computed_at": now.isoformat(),
        }
