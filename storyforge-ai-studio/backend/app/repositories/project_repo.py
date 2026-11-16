"""Project and MediaAsset repository — all DB access goes through here."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    EditManifest,
    Job,
    MediaAsset,
    MediaRole,
    MediaStatus,
    Project,
    ProjectStatus,
    RenderJob,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def create_project(
    db: Session,
    *,
    owner_id: str,
    title: str,
    language_preference: str = "auto",
    output_preset: str = "reels",
) -> Project:
    project = Project(
        owner_id=owner_id,
        title=title,
        language_preference=language_preference,
        output_preset=output_preset,
        status=ProjectStatus.active,
    )
    db.add(project)
    db.flush()
    return project


def get_project(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def get_project_owned_by(db: Session, project_id: str, owner_id: str) -> Project | None:
    """Return project only when it belongs to owner_id. IDOR guard."""
    stmt = select(Project).where(
        Project.id == project_id,
        Project.owner_id == owner_id,
        Project.status != ProjectStatus.deleted,
    )
    return db.scalar(stmt)


def list_projects(
    db: Session, owner_id: str, limit: int = 20, cursor: str | None = None
) -> tuple[list[Project], int, str | None]:
    """Newest first. The cursor is an opaque offset; returns (rows, total, next_cursor)."""
    where = (Project.owner_id == owner_id, Project.status == ProjectStatus.active)
    total = db.scalar(select(func.count()).select_from(Project).where(*where)) or 0
    try:
        offset = max(int(cursor), 0) if cursor else 0
    except ValueError:
        offset = 0
    stmt = (
        select(Project)
        .where(*where)
        .order_by(Project.created_at.desc(), Project.id)
        .offset(offset)
        .limit(limit)
    )
    rows = list(db.scalars(stmt))
    next_cursor = str(offset + limit) if offset + limit < total else None
    return rows, total, next_cursor


def update_project(
    db: Session,
    project: Project,
    *,
    title: str | None = None,
    language_preference: str | None = None,
    output_preset: str | None = None,
) -> Project:
    if title is not None:
        project.title = title
    if language_preference is not None:
        project.language_preference = language_preference
    if output_preset is not None:
        project.output_preset = output_preset
    project.updated_at = _now()
    db.flush()
    return project


def mark_project_deleting(db: Session, project: Project) -> Project:
    project.status = ProjectStatus.deleting
    project.deleted_at = _now()
    project.updated_at = _now()
    db.flush()
    return project


# ---------------------------------------------------------------------------
# MediaAssets
# ---------------------------------------------------------------------------


def create_media_asset(
    db: Session,
    *,
    project_id: str,
    role: str = "primary",
    original_filename: str,
    content_type: str,
    expected_bytes: int,
) -> MediaAsset:
    asset = MediaAsset(
        project_id=project_id,
        role=MediaRole(role),
        status=MediaStatus.pending,
        original_filename=original_filename,
        content_type=content_type,
        file_size_bytes=expected_bytes,
    )
    db.add(asset)
    db.flush()
    return asset


def get_media_asset(db: Session, asset_id: str) -> MediaAsset | None:
    return db.get(MediaAsset, asset_id)


def get_media_asset_owned_by(db: Session, asset_id: str, owner_id: str) -> MediaAsset | None:
    """Return media asset only when its project belongs to owner_id."""
    stmt = (
        select(MediaAsset)
        .join(Project, MediaAsset.project_id == Project.id)
        .where(
            MediaAsset.id == asset_id,
            Project.owner_id == owner_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    return db.scalar(stmt)


def list_media_assets(db: Session, project_id: str) -> list[MediaAsset]:
    stmt = (
        select(MediaAsset)
        .where(
            MediaAsset.project_id == project_id,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at)
    )
    return list(db.scalars(stmt))


def update_media_asset_status(
    db: Session, asset: MediaAsset, status: MediaStatus, **kwargs: object
) -> MediaAsset:
    asset.status = status
    for k, v in kwargs.items():
        setattr(asset, k, v)
    asset.updated_at = _now()
    db.flush()
    return asset


def get_primary_media_asset(db: Session, project_id: str) -> MediaAsset | None:
    stmt = (
        select(MediaAsset)
        .where(
            MediaAsset.project_id == project_id,
            MediaAsset.role == MediaRole.primary,
            MediaAsset.status == MediaStatus.ready,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at)
    )
    return db.scalar(stmt)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def create_job(
    db: Session,
    *,
    project_id: str,
    job_type: str,
    media_asset_id: str | None = None,
    idempotency_key: str | None = None,
) -> Job:
    from app.db.models import JobStatus, JobType

    job = Job(
        project_id=project_id,
        job_type=JobType(job_type),
        status=JobStatus.created,
        media_asset_id=media_asset_id,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    db.flush()
    return job


def get_job(db: Session, job_id: str) -> Job | None:
    return db.get(Job, job_id)


def get_job_by_idempotency(db: Session, project_id: str, idempotency_key: str) -> Job | None:
    stmt = select(Job).where(
        Job.project_id == project_id,
        Job.idempotency_key == idempotency_key,
    )
    return db.scalar(stmt)


def update_job(db: Session, job: Job, **kwargs: object) -> Job:
    for k, v in kwargs.items():
        setattr(job, k, v)
    job.updated_at = _now()
    db.flush()
    return job


# ---------------------------------------------------------------------------
# Render jobs
# ---------------------------------------------------------------------------


def create_render_job(
    db: Session,
    *,
    project_id: str,
    manifest_id: str,
    preset: str = "preview",
) -> RenderJob:
    from app.db.models import JobStatus, RenderPreset

    rj = RenderJob(
        project_id=project_id,
        manifest_id=manifest_id,
        preset=RenderPreset(preset),
        status=JobStatus.created,
    )
    db.add(rj)
    db.flush()
    return rj


def get_render_job(db: Session, render_job_id: str) -> RenderJob | None:
    return db.get(RenderJob, render_job_id)


def list_render_jobs(db: Session, project_id: str) -> list[RenderJob]:
    stmt = (
        select(RenderJob)
        .where(RenderJob.project_id == project_id)
        .order_by(RenderJob.created_at.desc())
    )
    return list(db.scalars(stmt))


# ---------------------------------------------------------------------------
# Edit manifest
# ---------------------------------------------------------------------------


def get_latest_manifest(db: Session, project_id: str) -> EditManifest | None:
    stmt = (
        select(EditManifest)
        .where(EditManifest.project_id == project_id)
        .order_by(EditManifest.version.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def get_manifest_by_version(db: Session, project_id: str, version: int) -> EditManifest | None:
    stmt = select(EditManifest).where(
        EditManifest.project_id == project_id,
        EditManifest.version == version,
    )
    return db.scalar(stmt)


def save_manifest(
    db: Session,
    *,
    project_id: str,
    manifest_json: dict,
    expected_version: int,
) -> EditManifest:
    """Save a new manifest version. Raises ValueError on stale expected_version."""
    current = get_latest_manifest(db, project_id)
    current_version = current.version if current else 0

    if current_version != expected_version:
        raise ValueError(
            f"Manifest version conflict: expected {expected_version}, "
            f"server has {current_version}. Reload and retry."
        )

    new_version = current_version + 1
    manifest_json["version"] = new_version
    manifest = EditManifest(
        project_id=project_id,
        version=new_version,
        manifest_json=manifest_json,
    )
    db.add(manifest)
    db.flush()
    return manifest
