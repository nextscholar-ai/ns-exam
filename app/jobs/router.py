"""Jobs router (Phase 7 §5.7 / §7). Only endpoint in v1: poll job status.
Job *creation* happens inside whichever module triggers the async work
(e.g. Paper Generation, Phase 11) - it calls `job_registry.create(...)` and
returns 202 + this same job_id shape, never a separate creation endpoint here."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import NotFoundError
from app.jobs.registry import job_registry
from app.jobs.schemas import JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
    return JobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
