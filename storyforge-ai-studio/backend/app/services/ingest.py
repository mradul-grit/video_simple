"""Media ingest validation, run by a worker (never inside an HTTP request)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Job, JobStatus, MediaAsset, MediaStatus
from app.media.probe import MediaProbeError, MediaProbeTimeout, probe, validate_file_signature
from app.storage.local import LocalFilesystemStorage

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(db: Session, asset: MediaAsset, job: Job | None, message: str, code: str) -> None:
    asset.status = MediaStatus.failed
    if job is not None:
        job.status = JobStatus.failed
        job.message = message
        job.error_code = code
        job.progress = 100
    db.commit()


def validate_media_asset(
    db: Session, storage: LocalFilesystemStorage, asset: MediaAsset, job: Job | None = None
) -> MediaAsset:
    """Validate signature, size, streams and duration; persist metadata.

    Failure messages are safe to show to users (no paths or stack traces).
    """
    asset.status = MediaStatus.validating
    if job is not None:
        job.status = JobStatus.running
        job.stage = "validating"
        job.progress = 20
    db.commit()

    key = asset.storage_key
    if not key or not storage.exists(key):
        _fail(db, asset, job, "The uploaded file could not be found.", "UPLOAD_MISSING")
        return asset
    path = storage.get_path(key)

    size = path.stat().st_size
    if size > settings.max_upload_bytes:
        storage.delete_object(key)
        _fail(db, asset, job, "The file is larger than the allowed upload size.", "TOO_LARGE")
        return asset

    try:
        validate_file_signature(path, asset.content_type)
        meta = probe(path, timeout=settings.ffprobe_timeout_seconds)
    except MediaProbeTimeout:
        # Infrastructure problem: keep the original so validation can be retried.
        asset.status = MediaStatus.uploaded
        if job is not None:
            job.status = JobStatus.failed
            job.error_code = "PROBE_TIMEOUT"
            job.message = "Checking your video took too long. Please try again in a moment."
            job.progress = 100
        db.commit()
        return asset
    except MediaProbeError as exc:
        storage.delete_object(key)
        _fail(db, asset, job, str(exc), "INVALID_MEDIA")
        return asset

    if not meta.has_video:
        storage.delete_object(key)
        _fail(db, asset, job, "The file has no video stream.", "NO_VIDEO")
        return asset
    if meta.duration_seconds <= 0:
        storage.delete_object(key)
        _fail(db, asset, job, "The video has no readable duration.", "NO_DURATION")
        return asset
    if meta.duration_seconds > settings.max_video_duration_seconds:
        limit_min = settings.max_video_duration_seconds // 60
        storage.delete_object(key)
        _fail(
            db,
            asset,
            job,
            f"The video is longer than the {limit_min} minute limit.",
            "TOO_LONG",
        )
        return asset

    asset.file_size_bytes = size
    asset.checksum_sha256 = sha256_file(path)
    asset.duration_seconds = meta.duration_seconds
    asset.width = meta.width
    asset.height = meta.height
    asset.fps = meta.fps
    asset.video_codec = meta.video_codec
    asset.audio_codec = meta.audio_codec
    asset.has_audio = meta.has_audio
    asset.orientation = meta.orientation
    asset.probe_metadata = meta.raw
    asset.status = MediaStatus.ready
    if job is not None:
        job.status = JobStatus.completed
        job.stage = "completed"
        job.progress = 100
        job.message = "Media validated"
        job.completed_at = datetime.now(UTC)
    db.commit()
    return asset
