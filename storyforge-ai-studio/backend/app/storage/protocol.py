"""Object storage protocol — backend-agnostic interface.

All adapters must implement ObjectStorageProtocol.
No business logic is coupled to a specific cloud provider.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStorageProtocol(Protocol):
    """Read/write interface for large binary objects (video, audio, images)."""

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        """Write bytes to storage at *key*. Key is controlled server-side."""
        ...

    def get_object(self, key: str) -> bytes:
        """Return raw bytes for *key*. Raises FileNotFoundError if absent."""
        ...

    def delete_object(self, key: str) -> None:
        """Remove *key*. Idempotent — no error if key already absent."""
        ...

    def exists(self, key: str) -> bool:
        """Return True if *key* exists in storage."""
        ...

    def signed_url(self, key: str, ttl_seconds: int) -> str:
        """Return a short-lived URL for GET access to *key*."""
        ...

    def signed_upload_url(self, key: str, ttl_seconds: int, max_bytes: int) -> str:
        """Return a short-lived URL for PUT upload of *key* with size cap."""
        ...
