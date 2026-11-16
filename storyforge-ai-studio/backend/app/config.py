from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_name: str = "StoryForge AI Studio"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://storyforge:storyforge_dev_only@localhost:5433/storyforge"
    redis_url: str = "redis://localhost:6380/0"
    storage_backend: str = "local"
    local_storage_root: str = "./media_data"
    max_upload_bytes: int = 1_073_741_824
    max_video_duration_seconds: int = 900
    signed_url_ttl_seconds: int = 300
    default_media_retention_days: int = 7
    transcription_provider: str = "mock"
    llm_provider: str = "mock"
    visual_search_provider: str = "openverse"
    image_generation_provider: str = "disabled"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
