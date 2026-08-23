"""
Jobs router (Phase 7 §5.7 / Phase 18 §2).

Endpoints:
  GET  /jobs/{job_id}              — poll job status (Phase 7).
  GET  /jobs/                      — list recent jobs (Phase 18).
  POST /jobs/bulk-question-import  — enqueue bulk question import (Phase 18).
  POST /jobs/batch-report          — enqueue batch report generation (Phase 18).
  POST /jobs/nightly-analytics     — enqueue nightly analytics recompute (Phase 18).

Job *creation* happens inside whichever module triggers the async work (e.g.
Paper Generation, Phase 11). The POST endpoints here are convenience triggers
for admin/teacher operations.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.core.exceptions import NotFoundError
from app.core.security.rbac import require_role
from app.jobs.registry import job_registry
from app.jobs.schemas import (
    BatchReportRequest,
    BulkImportRequest,
    JobEnqueueResponse,
    JobStatusResponse,
    NightlyAnalyticsRequest,
)

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_role("SUPER_ADMIN", "ADMIN", "SCHOOL_ADMIN", "TEACHER"))],
)


def _job_to_response(job) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        result=job.result,
        error=job.error,
        meta=job.meta,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get(
    "/",
    response_model=list[JobStatusResponse],
    summary="List recent background jobs",
)
async def list_jobs(limit: int = Query(default=20, ge=1, le=100)) -> list[JobStatusResponse]:
    """Return the `limit` most recently created background jobs (newest first)."""
    jobs = job_registry.list_recent(limit=limit)
    return [_job_to_response(j) for j in jobs]


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get the status of a background job",
    responses={404: {"description": "Job not found"}},
)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = job_registry.get(job_id)
    if job is None:
        raise NotFoundError(f"Job '{job_id}' not found")
    return _job_to_response(job)


@router.post(
    "/bulk-question-import",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a bulk question import job",
)
async def enqueue_bulk_question_import(
    body: BulkImportRequest,
) -> JobEnqueueResponse:
    """
    Accept a list of pre-parsed question dicts and import them asynchronously.
    Returns a job_id to poll for progress.
    """
    from app.jobs.tasks import launch_bulk_question_import
    job_id = launch_bulk_question_import(
        subject_id=body.subject_id,
        chapter_id=body.chapter_id,
        questions=body.questions,
    )
    return JobEnqueueResponse(job_id=job_id, job_type="BULK_QUESTION_IMPORT")


@router.post(
    "/batch-report",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue batch report generation for all students in an exam",
)
async def enqueue_batch_report(
    body: BatchReportRequest,
) -> JobEnqueueResponse:
    """
    Trigger asynchronous report generation for every student who sat `exam_id`.
    """
    from app.jobs.tasks import launch_batch_report_generation
    job_id = launch_batch_report_generation(
        exam_id=body.exam_id,
        report_type=body.report_type,
    )
    return JobEnqueueResponse(job_id=job_id, job_type="BATCH_REPORT_GENERATION")


@router.post(
    "/nightly-analytics",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger nightly analytics recomputation for a school",
)
async def enqueue_nightly_analytics(
    body: NightlyAnalyticsRequest,
) -> JobEnqueueResponse:
    """
    Recompute analytics dashboards for all active students in a school.
    Normally triggered by a cron job; this endpoint allows manual re-runs.
    """
    from app.jobs.tasks import launch_nightly_analytics_recompute
    job_id = launch_nightly_analytics_recompute(school_id=body.school_id)
    return JobEnqueueResponse(job_id=job_id, job_type="NIGHTLY_ANALYTICS_RECOMPUTE")
