"""Render and export endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.config import settings
from app.db.models import JobStatus
from app.domain.schemas import (
    DownloadUrlResponse,
    RenderEnqueueRequest,
    RenderJobOut,
)
from app.repositories.project_repo import (
    create_render_job,
    get_manifest_by_version,
    get_project_owned_by,
    get_render_job,
    list_render_jobs,
)
from app.storage.factory import get_storage

router = APIRouter(tags=["renders"])


def _assert_project(db, project_id, owner_id):
    p = get_project_owned_by(db, project_id, owner_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


@router.post("/projects/{project_id}/renders", response_model=RenderJobOut, status_code=202)
def enqueue_render(
    project_id: str,
    body: RenderEnqueueRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> RenderJobOut:
    _assert_project(db, project_id, current_user.id)

    manifest = get_manifest_by_version(db, project_id, body.manifest_version)
    if manifest is None:
        raise HTTPException(404, f"Manifest version {body.manifest_version} not found")

    rj = create_render_job(
        db,
        project_id=project_id,
        manifest_id=manifest.id,
        preset=body.preset,
    )
    db.commit()
    db.refresh(rj)

    rj.celery_task_id = rj.id
    rj.status = JobStatus.queued
    db.commit()
    try:
        from app.workers.tasks import run_render

        run_render.apply_async(args=[rj.id, project_id, manifest.id, body.preset], task_id=rj.id)
    except Exception as exc:
        rj.status = JobStatus.failed
        rj.message = "Render worker unavailable"
        db.commit()
        raise HTTPException(503, "Render worker unavailable") from exc

    db.refresh(rj)
    return RenderJobOut.model_validate(rj)


@router.get("/renders/{render_id}", response_model=RenderJobOut)
def get_render(
    render_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> RenderJobOut:
    rj = get_render_job(db, render_id)
    if rj is None:
        raise HTTPException(404, "Render job not found")
    # IDOR guard
    _assert_project(db, rj.project_id, current_user.id)
    return RenderJobOut.model_validate(rj)


@router.get("/projects/{project_id}/exports", response_model=list[RenderJobOut])
def list_exports(
    project_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> list[RenderJobOut]:
    _assert_project(db, project_id, current_user.id)
    rjs = list_render_jobs(db, project_id)
    return [RenderJobOut.model_validate(r) for r in rjs]


@router.post("/exports/{render_id}/download-url", response_model=DownloadUrlResponse)
def download_url(
    render_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> DownloadUrlResponse:
    rj = get_render_job(db, render_id)
    if rj is None:
        raise HTTPException(404, "Render job not found")
    _assert_project(db, rj.project_id, current_user.id)

    if rj.status != JobStatus.completed or not rj.output_storage_key:
        raise HTTPException(409, "Export is not ready for download")

    storage = get_storage()
    url = storage.signed_url(rj.output_storage_key, settings.signed_url_ttl_seconds)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.signed_url_ttl_seconds)
    return DownloadUrlResponse(url=url, expires_at=expires_at)
