from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRETS = {
    "local_dev_insecure_secret_change_in_production",
    "dev_insecure_secret_change_before_any_deployment",
    "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_name: str = "StoryForge AI Studio"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # Database
    database_url: str = (
        "postgresql+psycopg://storyforge:storyforge_dev_only@localhost:5433/storyforge"
    )
    redis_url: str = "redis://localhost:6380/0"

    # Storage
    storage_backend: str = "local"
    local_storage_root: str = "./media_data"
    storage_signing_secret: str = "local_dev_insecure_secret_change_in_production"

    # Canonical edit manifest schema; empty = search next to backend/ and the repo root
    manifest_schema_path: str = ""

    # Upload / processing safeguards
    max_upload_bytes: int = 1_073_741_824  # 1 GB
    max_video_duration_seconds: int = 900  # 15 min
    signed_url_ttl_seconds: int = 300
    default_media_retention_days: int = 7
    max_concurrent_jobs_per_user: int = 1

    # AI providers (mock = safe demo/test mode — never real output)
    transcription_provider: str = "mock"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    llm_provider: str = "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    visual_search_provider: str = "openverse"
    image_generation_provider: str = "disabled"
    comfyui_base_url: str = "http://localhost:8188"

    # Optional object storage (S3-compatible) — server-side only
    s3_endpoint_url: str = ""
    s3_region: str = "ap-south-1"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_force_path_style: bool = False

    # Optional provider keys (server-side only — never in mobile)
    pixabay_api_key: str = ""
    pexels_api_key: str = ""

    # Auth (dev-only stub until Phase 6)
    dev_auth_enabled: bool = True
    secret_key: str = "dev_insecure_secret_change_before_any_deployment"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 h

    @model_validator(mode="after")
    def _refuse_dev_secrets_outside_development(self) -> Settings:
        """Signing keys must be real secrets anywhere but a developer machine."""
        if self.app_env != "development":
            weak = [
                name
                for name in ("secret_key", "storage_signing_secret")
                if getattr(self, name) in _DEV_SECRETS or len(getattr(self, name)) < 32
            ]
            if weak:
                raise ValueError(
                    f"APP_ENV={self.app_env} needs strong values for: {', '.join(weak).upper()}"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
