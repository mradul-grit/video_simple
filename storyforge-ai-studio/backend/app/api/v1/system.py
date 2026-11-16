"""Public, non-sensitive server facts the client needs before it does anything.

Never add secrets, hostnames, keys or internal paths here.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.domain.schemas import ALLOWED_VIDEO_CONTENT_TYPES

router = APIRouter(prefix="/system", tags=["system"])


class ProviderInfo(BaseModel):
    transcription: str
    language_model: str
    visual_search: str
    image_generation: str
    demo_mode: bool  # True when any analysis provider returns labelled mock output


class SystemInfo(BaseModel):
    environment: str
    api_version: str
    max_upload_bytes: int
    max_video_duration_seconds: int
    accepted_content_types: list[str]
    media_retention_days: int
    providers: ProviderInfo


@router.get("/info", response_model=SystemInfo)
def system_info() -> SystemInfo:
    demo = settings.transcription_provider == "mock" or settings.llm_provider == "mock"
    return SystemInfo(
        environment=settings.app_env,
        api_version="v1",
        max_upload_bytes=settings.max_upload_bytes,
        max_video_duration_seconds=settings.max_video_duration_seconds,
        accepted_content_types=sorted(ALLOWED_VIDEO_CONTENT_TYPES),
        media_retention_days=settings.default_media_retention_days,
        providers=ProviderInfo(
            transcription=settings.transcription_provider,
            language_model=settings.llm_provider,
            visual_search=settings.visual_search_provider,
            image_generation=settings.image_generation_provider,
            demo_mode=demo,
        ),
    )
