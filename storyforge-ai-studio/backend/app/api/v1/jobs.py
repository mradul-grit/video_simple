"""Generic job status and control: GET /jobs/{id}, POST /jobs/{id}/cancel, POST /jobs/{id}/retry."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.api.ratelimit import per_user
from app.db.models import Job, JobStatus, JobType, MediaAsset, MediaStatus
from app.domain.schemas import JobStatusResponse
from app.repositories.project_repo import get_job, get_project_owned_by, update_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


def _owned_job(db, job_id: str, owner_id: str) -> Job:
    job = get_job(db, job_id)
    if job is None or get_project_owned_by(db, job.project_id, owner_id) is None:
        raise HTTPException(404, "Job not found")  # same answer for "missing" and "not yours"
    return job


def _dispatch(job: Job) -> None:
    """Queue the worker task for *job* under its own id (one logical job, many attempts)."""
    from app.workers.tasks import run_analysis, run_media_validation

    if job.job_type == JobType.media_validate:
        run_media_validation.apply_async(args=[job.id, job.media_asset_id], task_id=job.id)
    elif job.job_type == JobType.transcribe:
        run_analysis.apply_async(args=[job.id, job.project_id, job.media_asset_id], task_id=job.id)
    else:  # pragma: no cover - guarded by Job.retryable
        raise ValueError(f"cannot dispatch {job.job_type}")


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, current_user: CurrentUser, db: DbSession) -> JobStatusResponse:
    return JobStatusResponse.model_validate(_owned_job(db, job_id, current_user.id))


@router.post("/{job_id}/cancel", response_model=JobStatusResponse)
def cancel_job(job_id: str, current_user: CurrentUser, db: DbSession) -> JobStatusResponse:
    """Cancel a queued or running job. Workers never overwrite `cancelled` (see job_state)."""
    job = _owned_job(db, job_id, current_user.id)
    if job.status in (JobStatus.completed, JobStatus.cancelled, JobStatus.failed):
        raise HTTPException(409, f"Cannot cancel a job that is {job.status.value}")
    update_job(db, job, status=JobStatus.cancelled, message="Cancelled")
    db.commit()
    db.refresh(job)
    try:  # best effort: drop it from the queue if no worker has picked it up yet
        from app.workers.celery_app import celery_app

        celery_app.control.revoke(job.celery_task_id or job.id)
    except Exception:
        logger.warning("could not revoke task for job %s", job.id)
    return JobStatusResponse.model_validate(job)


@router.post(
    "/{job_id}/retry",
    response_model=JobStatusResponse,
    status_code=202,
    dependencies=[Depends(per_user("jobs:retry"))],
)
def retry_job(job_id: str, current_user: CurrentUser, db: DbSession) -> JobStatusResponse:
    """Re-run an eligible failed job as the next attempt of the same job (same id)."""
    job = _owned_job(db, job_id, current_user.id)
    if job.status != JobStatus.failed:
        raise HTTPException(
            409, f"Only failed jobs can be retried (this one is {job.status.value})"
        )
    if not job.retryable:
        reason = (
            "No retries left for this job."
            if job.retry_count >= job.max_retries
            else "This job can't be retried. Start it again instead."
        )
        raise HTTPException(409, reason)

    asset = db.get(MediaAsset, job.media_asset_id) if job.media_asset_id else None
    needed = MediaStatus.uploaded if job.job_type == JobType.media_validate else MediaStatus.ready
    if asset is None or asset.status != needed:
        raise HTTPException(409, "The video this job needs is no longer available.")

    update_job(
        db,
        job,
        status=JobStatus.queued,
        retry_count=job.retry_count + 1,
        error_code=None,
        message=None,
        stage=None,
        progress=0,
        completed_at=None,
    )
    db.commit()
    try:
        _dispatch(job)
    except Exception as exc:
        update_job(db, job, status=JobStatus.failed, message="Worker unavailable")
        db.commit()
        raise HTTPException(503, "Background worker unavailable. Try again shortly.") from exc
    db.refresh(job)
    return JobStatusResponse.model_validate(job)
