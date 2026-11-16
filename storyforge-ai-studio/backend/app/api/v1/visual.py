"""Visual suggestions endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.db.models import JobStatus, JobType, VisualLayout
from app.domain.schemas import (
    JobStatusResponse,
    VisualSearchRequest,
    VisualSelectRequest,
    VisualSuggestionOut,
)
from app.repositories.analysis_repo import (
    get_visual_suggestion,
    list_visual_suggestions,
)
from app.repositories.project_repo import (
    create_job,
    get_job_by_idempotency,
    get_project_owned_by,
    update_job,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["visual-suggestions"])


def _assert_project(db, project_id, owner_id):
    p = get_project_owned_by(db, project_id, owner_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


@router.post("/visual-suggestions", response_model=JobStatusResponse, status_code=202)
def enqueue_visual_search(
    project_id: str,
    body: VisualSearchRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> JobStatusResponse:
    _assert_project(db, project_id, current_user.id)

    existing = get_job_by_idempotency(db, project_id, body.idempotency_key)
    if existing is not None:
        return JobStatusResponse.model_validate(existing)

    job = create_job(
        db,
        project_id=project_id,
        job_type=JobType.visual_search.value,
        idempotency_key=body.idempotency_key,
    )
    db.commit()
    db.refresh(job)

    update_job(db, job, status=JobStatus.queued, celery_task_id=job.id)
    db.commit()
    try:
        from app.workers.tasks import run_visual_search

        run_visual_search.apply_async(
            args=[job.id, project_id, body.story_beat_ids],
            task_id=job.id,
        )
    except Exception as exc:
        update_job(db, job, status=JobStatus.failed, message="Worker unavailable")
        db.commit()
        raise HTTPException(503, "Visual search worker unavailable") from exc

    db.refresh(job)
    return JobStatusResponse.model_validate(job)


@router.get("/visual-suggestions", response_model=list[VisualSuggestionOut])
def list_suggestions(
    project_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> list[VisualSuggestionOut]:
    _assert_project(db, project_id, current_user.id)
    suggestions = list_visual_suggestions(db, project_id)
    return [VisualSuggestionOut.model_validate(s) for s in suggestions]


@router.post("/visual-suggestions/{suggestion_id}/select", response_model=VisualSuggestionOut)
def select_suggestion(
    project_id: str,
    suggestion_id: str,
    body: VisualSelectRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> VisualSuggestionOut:
    _assert_project(db, project_id, current_user.id)
    suggestion = get_visual_suggestion(db, suggestion_id, project_id)
    if suggestion is None:
        raise HTTPException(404, "Suggestion not found")

    suggestion.selected = True
    suggestion.layout = VisualLayout(body.layout)
    suggestion.suggested_start_seconds = body.start_seconds
    suggestion.suggested_end_seconds = body.end_seconds
    db.commit()
    db.refresh(suggestion)
    return VisualSuggestionOut.model_validate(suggestion)
