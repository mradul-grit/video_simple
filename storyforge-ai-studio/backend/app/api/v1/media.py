"""Media ingest endpoints: upload grant, complete, list, delete.

Upload flow (same shape locally and with S3/R2 presigned URLs):
1. POST /upload-url  -> media row (pending) + short-lived upload URL
2. PUT  <upload_url> -> bytes land in private storage
3. POST /complete    -> enqueue validation job (ffprobe runs in a worker)
4. GET  /jobs/{id}   -> poll until the media asset is ready
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.config import settings
from app.db.models import JobStatus, JobType, MediaStatus
from app.domain.schemas import (
    DownloadUrlResponse,
    JobStatusResponse,
    MediaAssetOut,
    UploadCompleteRequest,
    UploadIntentRequest,
    UploadIntentResponse,
)
from app.repositories.project_repo import (
    create_job,
    create_media_asset,
    get_job_by_idempotency,
    get_media_asset_owned_by,
    get_project_owned_by,
    list_media_assets,
    update_job,
    update_media_asset_status,
)
from app.storage.factory import get_storage

router = APIRouter(prefix="/projects/{project_id}/media", tags=["media"])


def _assert_project(db, project_id: str, owner_id: str):
    project = get_project_owned_by(db, project_id, owner_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/upload-url", response_model=UploadIntentResponse, status_code=201)
def upload_intent(
    project_id: str,
    body: UploadIntentRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> UploadIntentResponse:
    _assert_project(db, project_id, current_user.id)

    if body.role not in ("primary", "b_roll"):
        raise HTTPException(422, "role must be 'primary' or 'b_roll'")
    if body.expected_bytes > settings.max_upload_bytes:
        raise HTTPException(
            413,
            f"File is larger than the {settings.max_upload_bytes // (1024 * 1024)} MB limit.",
        )

    asset = create_media_asset(
        db,
        project_id=project_id,
        role=body.role,
        original_filename=body.filename,
        content_type=body.content_type,
        expected_bytes=body.expected_bytes,
    )
    # Server-chosen key: user-supplied filename never touches the filesystem path.
    asset.storage_key = f"projects/{project_id}/media/{asset.id}/original"
    db.commit()

    upload_url = get_storage().signed_upload_url(
        asset.storage_key,
        ttl_seconds=settings.signed_url_ttl_seconds,
        max_bytes=body.expected_bytes,
    )
    return UploadIntentResponse(
        media_asset_id=asset.id,
        upload_url=upload_url,
        upload_method="PUT",
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.signed_url_ttl_seconds),
    )


@router.post("/complete", response_model=JobStatusResponse, status_code=202)
def complete_upload(
    project_id: str,
    body: UploadCompleteRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> JobStatusResponse:
    _assert_project(db, project_id, current_user.id)
    asset = get_media_asset_owned_by(db, body.media_asset_id, current_user.id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(404, "Media asset not found")

    key = f"validate:{asset.id}"
    existing = get_job_by_idempotency(db, project_id, key)
    if existing is not None and not (existing.retryable and asset.status == MediaStatus.uploaded):
        return JobStatusResponse.model_validate(existing)

    if asset.status != MediaStatus.uploaded:
        raise HTTPException(409, f"Media asset is {asset.status.value}; upload it first.")

    if existing is not None:  # same logical job, next attempt
        job = existing
        update_job(
            db, job, retry_count=job.retry_count + 1, error_code=None, message=None, progress=0
        )
    else:
        job = create_job(
            db,
            project_id=project_id,
            job_type=JobType.media_validate.value,
            media_asset_id=asset.id,
            idempotency_key=key,
        )
    db.commit()

    update_job(db, job, status=JobStatus.queued, celery_task_id=job.id)
    db.commit()
    try:
        from app.workers.tasks import run_media_validation

        run_media_validation.apply_async(args=[job.id, asset.id], task_id=job.id)
    except Exception as exc:
        update_job(db, job, status=JobStatus.failed, message="Worker unavailable")
        db.commit()
        raise HTTPException(503, "Background worker unavailable. Try again shortly.") from exc

    db.refresh(job)
    return JobStatusResponse.model_validate(job)


@router.get("", response_model=list[MediaAssetOut])
def list_media(project_id: str, current_user: CurrentUser, db: DbSession) -> list[MediaAssetOut]:
    _assert_project(db, project_id, current_user.id)
    return [MediaAssetOut.model_validate(a) for a in list_media_assets(db, project_id)]


@router.post("/{media_id}/preview-url", response_model=DownloadUrlResponse)
def media_preview_url(
    project_id: str, media_id: str, current_user: CurrentUser, db: DbSession
) -> DownloadUrlResponse:
    """Short-lived link for the owner to play their original in the editor."""
    _assert_project(db, project_id, current_user.id)
    asset = get_media_asset_owned_by(db, media_id, current_user.id)
    if (
        asset is None
        or asset.project_id != project_id
        or asset.status != MediaStatus.ready
        or not asset.storage_key
    ):
        raise HTTPException(404, "Media asset not found")
    ttl = settings.signed_url_ttl_seconds
    return DownloadUrlResponse(
        url=get_storage().signed_url(asset.storage_key, ttl),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )


@router.delete("/{media_id}", status_code=204)
def delete_media(project_id: str, media_id: str, current_user: CurrentUser, db: DbSession) -> None:
    _assert_project(db, project_id, current_user.id)
    asset = get_media_asset_owned_by(db, media_id, current_user.id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(404, "Media asset not found")

    if asset.storage_key:
        get_storage().delete_object(asset.storage_key)
    update_media_asset_status(
        db, asset, MediaStatus.deleted, deleted_at=datetime.now(UTC), storage_key=None
    )
    db.commit()
