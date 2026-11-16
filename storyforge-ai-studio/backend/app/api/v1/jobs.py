"""Generic job status and control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.db.models import JobStatus
from app.domain.schemas import JobStatusResponse
from app.repositories.project_repo import (
    get_job,
    get_project_owned_by,
    update_job,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> JobStatusResponse:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    # IDOR guard: check ownership via project
    project = get_project_owned_by(db, job.project_id, current_user.id)
    if project is None:
        raise HTTPException(404, "Job not found")
    return JobStatusResponse.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobStatusResponse)
def cancel_job(
    job_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> JobStatusResponse:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    project = get_project_owned_by(db, job.project_id, current_user.id)
    if project is None:
        raise HTTPException(404, "Job not found")
    if job.status in (JobStatus.completed, JobStatus.cancelled, JobStatus.failed):
        raise HTTPException(409, f"Cannot cancel job in state {job.status.value}")
    update_job(db, job, status=JobStatus.cancelled)
    db.commit()
    db.refresh(job)
    return JobStatusResponse.model_validate(job)
