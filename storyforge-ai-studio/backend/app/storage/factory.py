"""Return the configured storage adapter based on settings.storage_backend."""

from __future__ import annotations

from app.config import settings
from app.storage.local import LocalFilesystemStorage


def get_storage() -> LocalFilesystemStorage:
    """FastAPI dependency. Returns the configured storage adapter."""
    if settings.storage_backend == "local":
        return LocalFilesystemStorage()
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend!r}")
