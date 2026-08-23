"""
Core Event Handlers — Cross-Module Event Subscriptions (Phase 17 §5).

Architecture Contract (Phase 2 §10):
  - Handlers only consume the event *payload* (a plain dict).
  - Handlers NEVER import from another module's internals; they go through
    the target module's service layer (which owns its own DB session).
  - A failing handler is isolated by the EventBus (logged, not re-raised).
  - All handlers are async; the bus awaits them individually.

Handler chain:
  ExamSubmitted      → EvaluationService.create_from_attempt
  EvaluationCompleted → MasteryService.process_evaluation
  MasteryUpdated     → RecommendationService.generate_recommendation (background)
  LearningProfileUpdated → AnalyticsService.compute_dashboard (background)
  ReportGenerated    → (logged only — future: ERP sync hook)
"""
from __future__ import annotations

from typing import Any

from app.core.db.session import db_session_scope
from app.core.events.bus import event_bus
from app.core.events.event_names import (
    ANALYTICS_UPDATED,
    EVALUATION_COMPLETED,
    EXAM_SUBMITTED,
    LEARNING_PROFILE_UPDATED,
    MASTERY_UPDATED,
    REPORT_GENERATED,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ExamSubmitted → Evaluation intake
# ---------------------------------------------------------------------------

async def _on_exam_submitted(payload: dict[str, Any]) -> None:
    """
    Trigger evaluation creation when a student submits an attempt.

    Payload keys: attempt_public_id, exam_id, student_id, paper_id, submitted_at
    """
    attempt_public_id: str = payload.get("attempt_public_id", "")
    student_id: int | None = payload.get("student_id")

    if not attempt_public_id:
        logger.warning("handler.exam_submitted.missing_attempt_public_id")
        return

    # We need to resolve attempt_id from public_id to call the evaluation service
    async with db_session_scope() as session:
        from app.modules.exam_management.repository import StudentAttemptRepository
        from app.modules.evaluation.service import EvaluationService

        attempt_repo = StudentAttemptRepository(session)
        attempt = await attempt_repo.get_by(public_id=attempt_public_id)
        if attempt is None:
            logger.warning(
                "handler.exam_submitted.attempt_not_found",
                attempt_public_id=attempt_public_id,
            )
            return

        svc = EvaluationService(session)
        evaluation = await svc.get_or_create_evaluation(attempt.id)
        logger.info(
            "handler.exam_submitted.evaluation_created",
            attempt_public_id=attempt_public_id,
            evaluation_id=evaluation.id,
            student_id=student_id,
        )


# ---------------------------------------------------------------------------
# EvaluationCompleted → Mastery update
# ---------------------------------------------------------------------------

async def _on_evaluation_completed(payload: dict[str, Any]) -> None:
    """
    Trigger mastery update when an evaluation is locked/completed.

    Payload keys: evaluation_public_id, student_id, attempt_id
    """
    evaluation_public_id: str = payload.get("evaluation_public_id", "")
    if not evaluation_public_id:
        logger.warning("handler.evaluation_completed.missing_evaluation_public_id")
        return

    async with db_session_scope() as session:
        from app.modules.learning_profile.service import MasteryService
        svc = MasteryService(session)
        summary = await svc.process_evaluation(evaluation_public_id)
        if summary:
            logger.info(
                "handler.evaluation_completed.mastery_updated",
                evaluation_public_id=evaluation_public_id,
                topics_updated=summary.get("topics_updated", 0),
            )


# ---------------------------------------------------------------------------
# MasteryUpdated → Recommendation refresh (background, best-effort)
# ---------------------------------------------------------------------------

async def _on_mastery_updated(payload: dict[str, Any]) -> None:
    """
    Refresh a student's recommendations when their mastery changes.

    Payload keys: student_id, subject_id, mastery_score, topic_id
    """
    student_id: int | None = payload.get("student_id")
    subject_id: int | None = payload.get("subject_id")

    if not student_id or not subject_id:
        logger.warning(
            "handler.mastery_updated.skipped_missing_ids",
            payload_keys=list(payload.keys()),
        )
        return

    async with db_session_scope() as session:
        from app.modules.recommendation.service import RecommendationService
        from app.modules.learning_profile.service import LearningProfileService
        profile_svc = LearningProfileService(session)
        rec_svc = RecommendationService(session, profile_service=profile_svc)
        result = await rec_svc.generate_recommendation(
            student_id=student_id,
            subject_id=subject_id,
        )
        logger.info(
            "handler.mastery_updated.recommendation_refreshed",
            student_id=student_id,
            subject_id=subject_id,
            recommendation_public_id=result.get("public_id") if result else None,
        )


# ---------------------------------------------------------------------------
# LearningProfileUpdated → Analytics dashboard refresh (best-effort)
# ---------------------------------------------------------------------------

async def _on_learning_profile_updated(payload: dict[str, Any]) -> None:
    """
    Refresh the analytics dashboard when a student's profile changes.

    Payload keys: student_id, updated_at, subjects_updated
    """
    student_id: int | None = payload.get("student_id")

    if not student_id:
        logger.warning("handler.learning_profile_updated.missing_student_id")
        return

    async with db_session_scope() as session:
        from app.modules.analytics.service import AnalyticsService
        svc = AnalyticsService(session)
        await svc.get_student_dashboard(student_id)
        logger.info(
            "handler.learning_profile_updated.analytics_refreshed",
            student_id=student_id,
        )


# ---------------------------------------------------------------------------
# AnalyticsUpdated → (future: push notification / ERP sync)
# ---------------------------------------------------------------------------

async def _on_analytics_updated(payload: dict[str, Any]) -> None:
    """Phase 18: dispatch at-risk alert notification when student is flagged."""
    student_id: int | None = payload.get("student_id")
    is_at_risk: bool = bool(payload.get("is_at_risk", False))

    logger.info(
        "handler.analytics_updated.received",
        student_id=student_id,
        is_at_risk=is_at_risk,
    )

    if is_at_risk and student_id:
        from app.core.notifications import notification_dispatcher
        await notification_dispatcher.send_at_risk_alert(
            student_id=student_id,
        )


# ---------------------------------------------------------------------------
# ReportGenerated → (future: delivery / notification)
# ---------------------------------------------------------------------------

async def _on_report_generated(payload: dict[str, Any]) -> None:
    """Phase 18: notify student that their report is ready for download."""
    report_public_id: str | None = payload.get("report_public_id")
    report_type: str = str(payload.get("report_type", "UNKNOWN"))
    student_id: int | None = payload.get("student_id")

    logger.info(
        "handler.report_generated.received",
        report_public_id=report_public_id,
        report_type=report_type,
    )

    if student_id and report_public_id:
        from app.core.notifications import notification_dispatcher
        await notification_dispatcher.send_report_ready(
            student_id=student_id,
            report_public_id=report_public_id,
            report_type=report_type,
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_all_handlers() -> None:
    """
    Subscribe all cross-module handlers to the in-process EventBus.

    Called once from `app.main` lifespan on startup.
    Double-registration is safe (idempotent list append) but should be
    avoided by ensuring this is called exactly once.
    """
    event_bus.subscribe(EXAM_SUBMITTED, _on_exam_submitted)
    event_bus.subscribe(EVALUATION_COMPLETED, _on_evaluation_completed)
    event_bus.subscribe(MASTERY_UPDATED, _on_mastery_updated)
    event_bus.subscribe(LEARNING_PROFILE_UPDATED, _on_learning_profile_updated)
    event_bus.subscribe(ANALYTICS_UPDATED, _on_analytics_updated)
    event_bus.subscribe(REPORT_GENERATED, _on_report_generated)

    logger.info("event_bus.handlers_registered", count=6)
