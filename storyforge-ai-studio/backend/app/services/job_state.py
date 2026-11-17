"""Atomic job state transitions shared by the API and the workers.

A worker must never overwrite a user's cancellation. Every worker-side change is a
conditional UPDATE that only applies while the job is still active, so a cancel that
lands between two worker steps always wins.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus, RenderJob

ACTIVE_STATUSES = (JobStatus.created, JobStatus.queued, JobStatus.running, JobStatus.retrying)


def advance(db: Session, job_id: str, **values: Any) -> bool:
    """Update an active job. Returns False when it is no longer active (e.g. cancelled).

    Does not commit: callers commit so that results and the final status can share
    one transaction.
    """
    values["updated_at"] = datetime.now(UTC)
    result = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(ACTIVE_STATUSES))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return bool(getattr(result, "rowcount", 0) == 1)


def advance_render(db: Session, render_id: str, **values: Any) -> bool:
    """Same rule for render jobs."""
    values["updated_at"] = datetime.now(UTC)
    result = db.execute(
        update(RenderJob)
        .where(RenderJob.id == render_id, RenderJob.status.in_(ACTIVE_STATUSES))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return bool(getattr(result, "rowcount", 0) == 1)


def is_active(db: Session, job_id: str) -> bool:
    status = db.query(Job.status).filter(Job.id == job_id).scalar()
    return status in ACTIVE_STATUSES
