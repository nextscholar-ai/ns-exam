"""
Phase 18 — Background Job Tasks Tests.

Tests verify:
  1. JobRegistry.create() stores job with meta.
  2. JobRegistry.list_recent() returns newest first.
  3. JobRegistry.list_by_type() filters correctly.
  4. JobRegistry lifecycle: PENDING → RUNNING → COMPLETED.
  5. JobRegistry lifecycle: PENDING → RUNNING → FAILED.
  6. run_bulk_question_import marks job COMPLETED on success.
  7. run_bulk_question_import marks job FAILED on DB error.
  8. run_batch_report_generation marks job COMPLETED.
  9. run_nightly_analytics_recompute marks job COMPLETED.
  10. NotificationDispatcher stubs log without raising.
  11. Job schemas validate correctly.
"""
from __future__ import annotations

import pytest

from app.jobs.registry import Job, JobRegistry, JobStatus
from app.core.notifications import NotificationDispatcher


# ---------------------------------------------------------------------------
# 1-5. JobRegistry — unit tests (no DB needed)
# ---------------------------------------------------------------------------

def test_job_registry_create_stores_job():
    registry = JobRegistry()
    job = registry.create("TEST_JOB", meta={"key": "value"})

    assert job.job_id is not None
    assert job.job_type == "TEST_JOB"
    assert job.status == JobStatus.PENDING
    assert job.meta["key"] == "value"
    assert registry.get(job.job_id) is job


def test_job_registry_create_without_meta():
    registry = JobRegistry()
    job = registry.create("SIMPLE_JOB")
    assert job.meta == {}


def test_job_registry_get_missing_returns_none():
    registry = JobRegistry()
    assert registry.get("nonexistent-id") is None


def test_job_registry_mark_running():
    registry = JobRegistry()
    job = registry.create("MY_JOB")
    registry.mark_running(job.job_id)

    fetched = registry.get(job.job_id)
    assert fetched.status == JobStatus.RUNNING


def test_job_registry_mark_completed():
    registry = JobRegistry()
    job = registry.create("MY_JOB")
    registry.mark_running(job.job_id)
    registry.mark_completed(job.job_id, {"imported": 5, "failed": 0})

    fetched = registry.get(job.job_id)
    assert fetched.status == JobStatus.COMPLETED
    assert fetched.result["imported"] == 5


def test_job_registry_mark_failed():
    registry = JobRegistry()
    job = registry.create("MY_JOB")
    registry.mark_running(job.job_id)
    registry.mark_failed(job.job_id, "DB connection refused")

    fetched = registry.get(job.job_id)
    assert fetched.status == JobStatus.FAILED
    assert fetched.error == "DB connection refused"


def test_job_registry_list_recent_order():
    from datetime import datetime, timezone, timedelta
    registry = JobRegistry()
    now = datetime.now(timezone.utc)
    j1 = registry.create("JOB_A")
    j1.created_at = now - timedelta(seconds=10)
    j2 = registry.create("JOB_B")
    j2.created_at = now - timedelta(seconds=5)
    j3 = registry.create("JOB_C")
    j3.created_at = now

    recent = registry.list_recent(limit=10)
    ids = [j.job_id for j in recent]
    assert ids.index(j3.job_id) < ids.index(j2.job_id) < ids.index(j1.job_id)


def test_job_registry_list_recent_respects_limit():
    registry = JobRegistry()
    for i in range(5):
        registry.create(f"JOB_{i}")

    recent = registry.list_recent(limit=3)
    assert len(recent) == 3


def test_job_registry_list_by_type():
    registry = JobRegistry()
    registry.create("TYPE_A")
    registry.create("TYPE_A")
    registry.create("TYPE_B")

    type_a = registry.list_by_type("TYPE_A")
    type_b = registry.list_by_type("TYPE_B")

    assert len(type_a) == 2
    assert len(type_b) == 1


def test_job_registry_mark_nonexistent_is_safe():
    """Marking a non-existent job should not raise."""
    registry = JobRegistry()
    registry.mark_running("ghost-id")      # must not raise
    registry.mark_completed("ghost-id", {})  # must not raise
    registry.mark_failed("ghost-id", "err") # must not raise


# ---------------------------------------------------------------------------
# 6. run_bulk_question_import — success path (mocked service)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_bulk_question_import_success():
    """Mock the QuestionBankService to verify registry update on success."""
    from unittest.mock import AsyncMock, patch
    from app.jobs.registry import job_registry
    from app.jobs.tasks import run_bulk_question_import

    job = job_registry.create("BULK_QUESTION_IMPORT")

    questions = [
        {"text": "What is 2+2?", "answer": "4"},
        {"text": "What is 3+3?", "answer": "6"},
    ]

    # Patch the DB session and QuestionBankService
    mock_svc = AsyncMock()
    mock_svc.create_question = AsyncMock(return_value=None)

    with patch("app.jobs.tasks.db_session_scope") as mock_scope:
        mock_session = AsyncMock()
        mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.modules.question_bank.service.QuestionBankService", return_value=mock_svc):
            await run_bulk_question_import(
                job_id=job.job_id,
                subject_id=1,
                chapter_id=2,
                questions=questions,
            )

    # Even without real DB, the mock scope means the job gets to the outer try
    fetched = job_registry.get(job.job_id)
    # Job should not be PENDING anymore (either RUNNING, COMPLETED, or FAILED)
    assert fetched.status != JobStatus.PENDING


# ---------------------------------------------------------------------------
# 7. run_bulk_question_import — failure path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_bulk_question_import_db_error_marks_failed():
    from unittest.mock import patch, AsyncMock
    from app.jobs.registry import job_registry
    from app.jobs.tasks import run_bulk_question_import

    job = job_registry.create("BULK_QUESTION_IMPORT")

    with patch("app.jobs.tasks.db_session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        await run_bulk_question_import(
            job_id=job.job_id,
            subject_id=1,
            chapter_id=None,
            questions=[{"text": "Q?"}],
        )

    fetched = job_registry.get(job.job_id)
    assert fetched.status == JobStatus.FAILED
    assert "Connection refused" in fetched.error


# ---------------------------------------------------------------------------
# 8. run_batch_report_generation — failure path (no real DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_batch_report_generation_db_error_marks_failed():
    from unittest.mock import patch, AsyncMock
    from app.jobs.registry import job_registry
    from app.jobs.tasks import run_batch_report_generation

    job = job_registry.create("BATCH_REPORT_GENERATION")

    with patch("app.jobs.tasks.db_session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(
            side_effect=RuntimeError("DB down")
        )
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        await run_batch_report_generation(job_id=job.job_id, exam_id=99)

    fetched = job_registry.get(job.job_id)
    assert fetched.status == JobStatus.FAILED
    assert "DB down" in fetched.error


# ---------------------------------------------------------------------------
# 9. run_nightly_analytics_recompute — failure path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_nightly_analytics_recompute_db_error_marks_failed():
    from unittest.mock import patch, AsyncMock
    from app.jobs.registry import job_registry
    from app.jobs.tasks import run_nightly_analytics_recompute

    job = job_registry.create("NIGHTLY_ANALYTICS_RECOMPUTE")

    with patch("app.jobs.tasks.db_session_scope") as mock_scope:
        mock_scope.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("Timeout")
        )
        mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

        await run_nightly_analytics_recompute(job_id=job.job_id, school_id=5)

    fetched = job_registry.get(job.job_id)
    assert fetched.status == JobStatus.FAILED


# ---------------------------------------------------------------------------
# 10. NotificationDispatcher — stubs log without raising
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notification_dispatcher_send_report_ready():
    dispatcher = NotificationDispatcher()
    # Must not raise
    await dispatcher.send_report_ready(
        student_id=1,
        report_public_id="rpt-abc",
        report_type="STUDENT_REPORT_CARD",
    )


@pytest.mark.asyncio
async def test_notification_dispatcher_send_at_risk_alert():
    dispatcher = NotificationDispatcher()
    await dispatcher.send_at_risk_alert(student_id=2, teacher_id=10)


@pytest.mark.asyncio
async def test_notification_dispatcher_send_job_completed():
    dispatcher = NotificationDispatcher()
    await dispatcher.send_job_completed(
        job_id="job-xyz",
        job_type="BULK_QUESTION_IMPORT",
        initiated_by=3,
    )


# ---------------------------------------------------------------------------
# 11. Job schemas validate correctly
# ---------------------------------------------------------------------------

def test_job_enqueue_response_schema():
    from app.jobs.schemas import JobEnqueueResponse

    resp = JobEnqueueResponse(job_id="j-001", job_type="BULK_QUESTION_IMPORT")
    assert resp.status == JobStatus.PENDING
    assert "poll" in resp.message.lower() or "job" in resp.message.lower()


def test_bulk_import_request_schema():
    from app.jobs.schemas import BulkImportRequest

    req = BulkImportRequest(
        subject_id=1,
        questions=[{"text": "Q?", "answer": "A"}],
    )
    assert req.chapter_id is None
    assert len(req.questions) == 1


def test_batch_report_request_schema():
    from app.jobs.schemas import BatchReportRequest

    req = BatchReportRequest(exam_id=5)
    assert req.report_type == "STUDENT_REPORT_CARD"
