"""SQLAlchemy ORM models for StoryForge AI Studio.

All timestamps are UTC. UUIDs are used as primary keys.
Binary media is never stored here — only metadata and object storage keys.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ProjectStatus(enum.StrEnum):
    active = "active"
    deleting = "deleting"
    deleted = "deleted"


class MediaRole(enum.StrEnum):
    primary = "primary"
    b_roll = "b_roll"


class MediaStatus(enum.StrEnum):
    pending = "pending"
    uploading = "uploading"
    uploaded = "uploaded"
    validating = "validating"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class JobType(enum.StrEnum):
    media_validate = "media_validate"
    transcribe = "transcribe"
    story_analyse = "story_analyse"
    visual_search = "visual_search"
    render = "render"


class JobStatus(enum.StrEnum):
    created = "created"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    retrying = "retrying"


RETRYABLE_ERROR_CODES = frozenset({"PROBE_TIMEOUT"})


class CaptionType(enum.StrEnum):
    verbatim = "verbatim"
    editorial = "editorial"


class VisualLayout(enum.StrEnum):
    picture_in_picture = "picture_in_picture"
    full_frame_cutaway = "full_frame_cutaway"


class RenderPreset(enum.StrEnum):
    preview = "preview"
    balanced = "balanced"
    high = "high"


# ---------------------------------------------------------------------------
# User (stub — full auth in Phase 6)
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    projects: Mapped[list[Project]] = relationship("Project", back_populates="owner")


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    language_preference: Mapped[str] = mapped_column(String(20), default="auto")
    output_preset: Mapped[str] = mapped_column(String(50), default="reels")
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.active, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User] = relationship("User", back_populates="projects")
    media_assets: Mapped[list[MediaAsset]] = relationship(
        "MediaAsset", back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        "Job", back_populates="project", cascade="all, delete-orphan"
    )
    edit_manifests: Mapped[list[EditManifest]] = relationship(
        "EditManifest", back_populates="project", cascade="all, delete-orphan"
    )
    render_jobs: Mapped[list[RenderJob]] = relationship(
        "RenderJob", back_populates="project", cascade="all, delete-orphan"
    )
    transcript_segments: Mapped[list[TranscriptSegment]] = relationship(
        "TranscriptSegment", back_populates="project", cascade="all, delete-orphan"
    )
    story_beats: Mapped[list[StoryBeat]] = relationship(
        "StoryBeat", back_populates="project", cascade="all, delete-orphan"
    )
    visual_suggestions: Mapped[list[VisualSuggestion]] = relationship(
        "VisualSuggestion", back_populates="project", cascade="all, delete-orphan"
    )
    cut_proposals: Mapped[list[CutProposal]] = relationship(
        "CutProposal", back_populates="project", cascade="all, delete-orphan"
    )
    editorial_captions: Mapped[list[EditorialCaption]] = relationship(
        "EditorialCaption", back_populates="project", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# MediaAsset
# ---------------------------------------------------------------------------


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MediaRole] = mapped_column(
        Enum(MediaRole), default=MediaRole.primary, nullable=False
    )
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus), default=MediaStatus.pending, nullable=False
    )
    # Object storage key (never a filesystem path with user input)
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    original_filename: Mapped[str | None] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(200))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))

    # ffprobe-extracted metadata
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    video_codec: Mapped[str | None] = mapped_column(String(50))
    audio_codec: Mapped[str | None] = mapped_column(String(50))
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    orientation: Mapped[int | None] = mapped_column(Integer)  # degrees rotation
    probe_metadata: Mapped[dict | None] = mapped_column(JSON)  # full ffprobe JSON

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship("Project", back_populates="media_assets")


# ---------------------------------------------------------------------------
# Job (generic async job)
# ---------------------------------------------------------------------------


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    job_type: Mapped[JobType] = mapped_column(Enum(JobType), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.created, nullable=False, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), index=True)
    stage: Mapped[str | None] = mapped_column(String(100))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    # Safe user-facing message; never include stack traces or secrets
    message: Mapped[str | None] = mapped_column(String(500))
    error_code: Mapped[str | None] = mapped_column(String(100))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    celery_task_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship("Project", back_populates="jobs")

    __table_args__ = (UniqueConstraint("project_id", "idempotency_key", name="uq_job_idempotency"),)

    @property
    def retryable(self) -> bool:
        """Failed for a transient reason and has retries left (exposed in job status)."""
        return (
            self.status == JobStatus.failed
            and self.error_code in RETRYABLE_ERROR_CODES
            and self.retry_count < self.max_retries
        )


# ---------------------------------------------------------------------------
# TranscriptSegment
# ---------------------------------------------------------------------------


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)  # ordering
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    is_speech: Mapped[bool] = mapped_column(Boolean, default=True)
    words: Mapped[list | None] = mapped_column(JSON)  # word-level timestamps when available

    project: Mapped[Project] = relationship("Project", back_populates="transcript_segments")


# ---------------------------------------------------------------------------
# StoryBeat
# ---------------------------------------------------------------------------


class StoryBeat(Base):
    __tablename__ = "story_beats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    # JSON list of transcript segment IDs that ground this beat
    transcript_segment_ids: Mapped[list] = mapped_column(JSON, default=list)
    visual_query_terms: Mapped[list] = mapped_column(JSON, default=list)
    visual_query_rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)

    project: Mapped[Project] = relationship("Project", back_populates="story_beats")


# ---------------------------------------------------------------------------
# CutProposal
# ---------------------------------------------------------------------------


class CutProposal(Base):
    __tablename__ = "cut_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    cut_type: Mapped[str] = mapped_column(String(50), nullable=False)  # pause|filler|silence
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # accepted=None means pending review; True=accepted; False=rejected
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    transcript_segment_ids: Mapped[list] = mapped_column(JSON, default=list)

    project: Mapped[Project] = relationship("Project", back_populates="cut_proposals")


# ---------------------------------------------------------------------------
# EditorialCaption
# ---------------------------------------------------------------------------


class EditorialCaption(Base):
    __tablename__ = "editorial_captions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Grounding: must reference transcript segment IDs
    transcript_segment_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    # low_confidence=True means flagged for human review before export
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    edited_text: Mapped[str | None] = mapped_column(Text)  # user override

    project: Mapped[Project] = relationship("Project", back_populates="editorial_captions")


# ---------------------------------------------------------------------------
# VisualSuggestion
# ---------------------------------------------------------------------------


class VisualSuggestion(Base):
    __tablename__ = "visual_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    story_beat_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("story_beats.id", ondelete="SET NULL"), nullable=True
    )
    # Provider metadata — NEVER stripped; must survive to export
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500))
    preview_url: Mapped[str | None] = mapped_column(String(2048))
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    creator: Mapped[str | None] = mapped_column(String(500))
    license_spdx: Mapped[str | None] = mapped_column(String(200))  # e.g. CC-BY-4.0
    attribution_text: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Story relevance
    relevance_score: Mapped[float | None] = mapped_column(Float)
    suggested_start_seconds: Mapped[float | None] = mapped_column(Float)
    suggested_end_seconds: Mapped[float | None] = mapped_column(Float)
    # User decision
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    layout: Mapped[VisualLayout | None] = mapped_column(Enum(VisualLayout))
    # Local cached copy key (after user accepts and we download it)
    cached_storage_key: Mapped[str | None] = mapped_column(String(1024))

    project: Mapped[Project] = relationship("Project", back_populates="visual_suggestions")


# ---------------------------------------------------------------------------
# EditManifest
# ---------------------------------------------------------------------------


class EditManifest(Base):
    __tablename__ = "edit_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    # Full manifest JSON — validated against EDIT_MANIFEST.schema.json before save
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    project: Mapped[Project] = relationship("Project", back_populates="edit_manifests")

    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_manifest_version"),)


# ---------------------------------------------------------------------------
# RenderJob
# ---------------------------------------------------------------------------


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    manifest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("edit_manifests.id", ondelete="RESTRICT"), nullable=False
    )
    preset: Mapped[RenderPreset] = mapped_column(
        Enum(RenderPreset), default=RenderPreset.preview, nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.created, nullable=False, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str | None] = mapped_column(String(500))
    output_storage_key: Mapped[str | None] = mapped_column(String(1024))
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    output_duration_seconds: Mapped[float | None] = mapped_column(Float)
    # ffprobe output stored after successful render for auditability
    output_probe: Mapped[dict | None] = mapped_column(JSON)
    celery_task_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship("Project", back_populates="render_jobs")
    manifest: Mapped[EditManifest] = relationship("EditManifest")
