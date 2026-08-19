"""
Background Job Task Workers (Phase 18 §2).

Each `run_*` function is an async worker launched via `asyncio.create_task()`.
It updates `job_registry` with RUNNING → COMPLETED / FAILED states so the
`GET /api/v1/jobs/{job_id}` polling contract is honoured.

Architecture (Phase 2 §10):
  - Tasks run in-process (no Celery/Redis in v1 modular monolith).
  - Each task opens its own `db_session_scope` so it is not tied to any
    request's session lifetime.
  - Tasks are fire-and-forget — callers get the job_id back immediately.
"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from app.core.db.session import db_session_scope
from app.core.logging import get_logger
from app.core.notifications import notification_dispatcher
from app.jobs.registry import job_registry

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Bulk Question Import
# ---------------------------------------------------------------------------

async def run_bulk_question_import(
    job_id: str,
    subject_id: int,
    chapter_id: int | None,
    questions: list[dict[str, Any]],
    actor_id: int | None = None,
) -> None:
    """
    Import a batch of questions into the Question Bank.

    `questions` is a list of pre-parsed question dicts (produced by the
    DOCX parser or upload endpoint). Each dict must satisfy the
    `QuestionBankService.create_question()` payload contract.

    Job meta: subject_id, chapter_id, total_questions
    """
    job_registry.mark_running(job_id)
    logger.info(
        "job.bulk_question_import.started",
        job_id=job_id,
        total=len(questions),
        actor_id=actor_id,
    )

    imported = 0
    failed_indices: list[int] = []

    try:
        async with db_session_scope() as session:
            from app.modules.question_bank.service import QuestionBankService
            svc = QuestionBankService(session)

            for idx, q_data in enumerate(questions):
                try:
                    await svc.create_question(
                        subject_id=subject_id,
                        chapter_id=chapter_id or q_data.get("chapter_id"),
                        **{k: v for k, v in q_data.items() if k not in ("subject_id", "chapter_id")},
                    )
                    imported += 1
                except Exception as exc:
                    logger.warning(
                        "job.bulk_question_import.item_failed",
                        job_id=job_id,
                        index=idx,
                        error=str(exc),
                    )
                    failed_indices.append(idx)

        result = {
            "imported": imported,
            "failed": len(failed_indices),
            "failed_indices": failed_indices,
            "total": len(questions),
        }
        job_registry.mark_completed(job_id, result)
        logger.info("job.bulk_question_import.completed", job_id=job_id, **result)

        if actor_id:
            await notification_dispatcher.send_job_completed(
                job_id=job_id, job_type="BULK_QUESTION_IMPORT", initiated_by=actor_id
            )

    except Exception as exc:
        error_msg = str(exc)
        job_registry.mark_failed(job_id, error_msg)
        logger.error("job.bulk_question_import.failed", job_id=job_id, error=error_msg)


# ---------------------------------------------------------------------------
# Batch Report Generation
# ---------------------------------------------------------------------------

async def run_batch_report_generation(
    job_id: str,
    exam_id: int,
    report_type: str = "STUDENT_REPORT_CARD",
    actor_id: int | None = None,
) -> None:
    """
    Generate report snapshots for every student who sat an exam.

    Steps:
      1. Fetch all student attempts for exam_id.
      2. For each attempt, call ReportService.generate_student_report_card().
      3. Collect results and mark job COMPLETED/FAILED.
    """
    job_registry.mark_running(job_id)
    logger.info(
        "job.batch_report_generation.started",
        job_id=job_id,
        exam_id=exam_id,
        report_type=report_type,
    )

    generated = 0
    failed_student_ids: list[int] = []

    try:
        async with db_session_scope() as session:
            from app.modules.exam_management.models import Exam, StudentAttempt
            from app.modules.exam_management.repository import StudentAttemptRepository
            from app.modules.reports.service import ReportService

            attempt_repo = StudentAttemptRepository(session)
            report_svc = ReportService(session)

            # Fetch all submitted attempts for this exam
            attempts = await attempt_repo.get_many(
                filters={"exam_id": exam_id, "status": "SUBMITTED"}
            )

            for attempt in attempts:
                try:
                    subject_id = (
                        await session.execute(
                            select(Exam.subject_id).where(Exam.id == attempt.exam_id)
                        )
                    ).scalar_one_or_none()
                    if subject_id is None:
                        raise ValueError(f"No subject for exam {attempt.exam_id}")
                    await report_svc.generate_student_report_card(
                        student_id=attempt.student_id,
                        subject_id=subject_id,
                    )
                    generated += 1
                except Exception as exc:
                    logger.warning(
                        "job.batch_report_generation.student_failed",
                        job_id=job_id,
                        student_id=attempt.student_id,
                        error=str(exc),
                    )
                    failed_student_ids.append(attempt.student_id)

        result = {
            "generated": generated,
            "failed": len(failed_student_ids),
            "failed_student_ids": failed_student_ids,
            "exam_id": exam_id,
            "report_type": report_type,
        }
        job_registry.mark_completed(job_id, result)
        logger.info("job.batch_report_generation.completed", job_id=job_id, **result)

        if actor_id:
            await notification_dispatcher.send_job_completed(
                job_id=job_id, job_type="BATCH_REPORT_GENERATION", initiated_by=actor_id
            )

    except Exception as exc:
        error_msg = str(exc)
        job_registry.mark_failed(job_id, error_msg)
        logger.error("job.batch_report_generation.failed", job_id=job_id, error=error_msg)


# ---------------------------------------------------------------------------
# Nightly Analytics Recomputation
# ---------------------------------------------------------------------------

async def run_nightly_analytics_recompute(
    job_id: str,
    school_id: int,
    actor_id: int | None = None,
) -> None:
    """
    Recompute analytics dashboards for all active students in a school.

    Called nightly (via cron / scheduled task). Iterates all active student
    profiles and refreshes their analytics dashboard data.
    """
    job_registry.mark_running(job_id)
    logger.info(
        "job.nightly_analytics_recompute.started",
        job_id=job_id,
        school_id=school_id,
    )

    processed = 0
    failed_student_ids: list[int] = []

    try:
        async with db_session_scope() as session:
            from app.modules.analytics.service import AnalyticsService
            from app.modules.student.repository import StudentRepository

            student_repo = StudentRepository(session)
            analytics_svc = AnalyticsService(session)

            students = await student_repo.list_active_by_school(school_id)

            for student in students:
                try:
                    subject_ids = await analytics_svc.get_student_subject_ids(student.id)
                    if not subject_ids:
                        continue
                    for subject_id in subject_ids:
                        await analytics_svc.get_student_dashboard(student.id, subject_id)
                    processed += 1
                except Exception as exc:
                    logger.warning(
                        "job.nightly_analytics_recompute.student_failed",
                        job_id=job_id,
                        student_id=student.id,
                        error=str(exc),
                    )
                    failed_student_ids.append(student.id)

        result = {
            "processed": processed,
            "failed": len(failed_student_ids),
            "failed_student_ids": failed_student_ids,
            "school_id": school_id,
        }
        job_registry.mark_completed(job_id, result)
        logger.info("job.nightly_analytics_recompute.completed", job_id=job_id, **result)

    except Exception as exc:
        error_msg = str(exc)
        job_registry.mark_failed(job_id, error_msg)
        logger.error("job.nightly_analytics_recompute.failed", job_id=job_id, error=error_msg)


# ---------------------------------------------------------------------------
# Task launcher helpers
# ---------------------------------------------------------------------------

def launch_bulk_question_import(
    subject_id: int,
    chapter_id: int | None,
    questions: list[dict[str, Any]],
    actor_id: int | None = None,
) -> str:
    """Enqueue bulk question import; returns job_id immediately."""
    job = job_registry.create(
        "BULK_QUESTION_IMPORT",
        meta={"subject_id": subject_id, "chapter_id": chapter_id, "count": len(questions)},
    )
    asyncio.create_task(
        run_bulk_question_import(job.job_id, subject_id, chapter_id, questions, actor_id)
    )
    return job.job_id


def launch_batch_report_generation(
    exam_id: int,
    report_type: str = "STUDENT_REPORT_CARD",
    actor_id: int | None = None,
) -> str:
    """Enqueue batch report generation; returns job_id immediately."""
    job = job_registry.create(
        "BATCH_REPORT_GENERATION",
        meta={"exam_id": exam_id, "report_type": report_type},
    )
    asyncio.create_task(
        run_batch_report_generation(job.job_id, exam_id, report_type, actor_id)
    )
    return job.job_id


def launch_nightly_analytics_recompute(
    school_id: int,
    actor_id: int | None = None,
) -> str:
    """Enqueue nightly analytics recompute; returns job_id immediately."""
    job = job_registry.create(
        "NIGHTLY_ANALYTICS_RECOMPUTE",
        meta={"school_id": school_id},
    )
    asyncio.create_task(
        run_nightly_analytics_recompute(job.job_id, school_id, actor_id)
    )
    return job.job_id
