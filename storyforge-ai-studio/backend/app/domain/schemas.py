"""Pydantic v2 request/response schemas for the StoryForge API.

These are the wire-format models. ORM models live in app.db.models.
Keep them separate so business logic is not tied to FastAPI or SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_VIDEO_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "video/x-matroska",
        "video/avi",
        "video/x-msvideo",
        "video/mpeg",
        "video/x-ms-wmv",
    }
)


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

REQUEST_ID_FIELD = Field(description="Server-generated request correlation ID")


class ApiError(BaseModel):
    code: str
    message: str
    field_errors: list[dict[str, str]] = []
    retryable: bool = False


class ErrorResponse(BaseModel):
    error: ApiError
    request_id: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    stage: str | None = None
    progress: int = 0
    message: str | None = None
    retryable: bool = False
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth (dev stub)
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DevLoginRequest(BaseModel):
    email: str
    display_name: str | None = None


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    language_preference: str = Field(default="auto", max_length=20)
    output_preset: str = Field(default="reels", max_length=50)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    language_preference: str | None = Field(default=None, max_length=20)
    output_preset: str | None = Field(default=None, max_length=50)


class ProjectOut(BaseModel):
    id: str
    owner_id: str
    title: str
    language_preference: str
    output_preset: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    items: list[ProjectOut]
    total: int
    cursor: str | None = None


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


class UploadIntentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=200)
    expected_bytes: int = Field(gt=0)
    role: str = Field(default="primary")

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed = ALLOWED_VIDEO_CONTENT_TYPES
        if v not in allowed:
            raise ValueError(
                f"Content type {v!r} is not supported. Allowed: {', '.join(sorted(allowed))}"
            )
        return v


class UploadIntentResponse(BaseModel):
    media_asset_id: str
    upload_url: str
    upload_method: str = "PUT"
    expires_at: datetime


class UploadCompleteRequest(BaseModel):
    media_asset_id: str
    checksum_sha256: str | None = None


class MediaAssetOut(BaseModel):
    id: str
    project_id: str
    role: str
    status: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class AnalysisEnqueueRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    media_asset_id: str | None = None  # defaults to primary asset


class TranscriptSegmentOut(BaseModel):
    id: str
    sequence: int
    start_seconds: float
    end_seconds: float
    text: str
    language: str | None
    confidence: float | None
    is_speech: bool
    words: list[dict[str, Any]] | None = None

    model_config = ConfigDict(from_attributes=True)


class CutProposalOut(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float
    reason: str
    cut_type: str
    confidence: float
    accepted: bool | None
    transcript_segment_ids: list[str]

    model_config = ConfigDict(from_attributes=True)


class EditorialCaptionOut(BaseModel):
    id: str
    sequence: int
    start_seconds: float
    end_seconds: float
    text: str
    transcript_segment_ids: list[str]
    confidence: float | None
    low_confidence: bool
    accepted: bool | None
    edited_text: str | None

    model_config = ConfigDict(from_attributes=True)


class StoryBeatOut(BaseModel):
    id: str
    sequence: int
    start_seconds: float
    end_seconds: float
    topic: str | None
    summary: str | None
    transcript_segment_ids: list[str]
    visual_query_terms: list[str]
    visual_query_rationale: str | None
    confidence: float | None

    model_config = ConfigDict(from_attributes=True)


class AnalysisResultResponse(BaseModel):
    transcript_segments: list[TranscriptSegmentOut]
    story_beats: list[StoryBeatOut]
    cut_proposals: list[CutProposalOut]
    editorial_captions: list[EditorialCaptionOut]
    language_detected: str | None
    language_confidence: float | None


# ---------------------------------------------------------------------------
# Cut proposal review
# ---------------------------------------------------------------------------


class CutProposalReviewRequest(BaseModel):
    accepted: bool
    start_seconds: float | None = None  # allow user to adjust handles
    end_seconds: float | None = None


# ---------------------------------------------------------------------------
# Visual suggestions
# ---------------------------------------------------------------------------


class VisualSearchRequest(BaseModel):
    story_beat_ids: list[str]
    idempotency_key: str = Field(min_length=1, max_length=200)


class VisualSuggestionOut(BaseModel):
    id: str
    provider: str
    external_id: str | None
    preview_url: str | None
    source_url: str
    creator: str | None
    license_spdx: str | None
    attribution_text: str | None
    relevance_score: float | None
    suggested_start_seconds: float | None
    suggested_end_seconds: float | None
    selected: bool
    layout: str | None

    model_config = ConfigDict(from_attributes=True)


class VisualSelectRequest(BaseModel):
    layout: str = Field(pattern="^(picture_in_picture|full_frame_cutaway)$")
    start_seconds: float
    end_seconds: float


# ---------------------------------------------------------------------------
# Edit manifest
# ---------------------------------------------------------------------------


class EditManifestOut(BaseModel):
    id: str
    project_id: str
    version: int
    schema_version: str
    manifest_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EditManifestSaveRequest(BaseModel):
    expected_version: int  # optimistic concurrency — must match current version
    manifest_json: dict[str, Any]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


class RenderEnqueueRequest(BaseModel):
    manifest_version: int
    preset: str = Field(default="preview", pattern="^(preview|balanced|high)$")


class RenderJobOut(BaseModel):
    id: str
    project_id: str
    preset: str
    status: str
    progress: int
    stage: str | None
    message: str | None
    output_size_bytes: int | None
    output_duration_seconds: float | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DownloadUrlResponse(BaseModel):
    url: str
    expires_at: datetime
