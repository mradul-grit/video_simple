"""Local filesystem object storage adapter.

For local development only, not production.
- Keys are sanitised to prevent path traversal.
- "Signed" URLs are HMAC-protected links served by this API (see api/v1/storage.py).
"""

from __future__ import annotations

import hashlib
import hmac
import shutil
import time
import urllib.parse
from pathlib import Path

from app.config import settings


def _safe_path(root: Path, key: str) -> Path:
    """Resolve *key* inside *root*, rejecting path traversal attempts."""
    clean = key.lstrip("/\\").replace("\\", "/")
    resolved = (root / clean).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path traversal detected for key: {key!r}")
    return resolved


class LocalFilesystemStorage:
    """Simple local filesystem adapter. Keys map to sub-paths under root_dir."""

    def __init__(self, root_dir: str | None = None) -> None:
        self._root = Path(root_dir or settings.local_storage_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def put_object(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        path = _safe_path(self._root, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_file(self, key: str, source: Path) -> None:
        """Move an already-written file into storage without loading it in memory."""
        path = _safe_path(self._root, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(path))

    def get_object(self, key: str) -> bytes:
        path = _safe_path(self._root, key)
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key!r}")
        return path.read_bytes()

    def delete_object(self, key: str) -> None:
        path = _safe_path(self._root, key)
        path.unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under *prefix*. Returns number of files removed."""
        path = _safe_path(self._root, prefix)
        if path == self._root or not path.exists():
            return 0
        count = sum(1 for p in path.rglob("*") if p.is_file())
        shutil.rmtree(path, ignore_errors=True)
        return count

    def exists(self, key: str) -> bool:
        try:
            return _safe_path(self._root, key).exists()
        except ValueError:
            return False

    def get_path(self, key: str) -> Path:
        """Return the absolute Path for *key*. Used internally by workers."""
        return _safe_path(self._root, key)

    # ------------------------------------------------------------------
    # Signed URLs (HMAC over method, key, expiry and size cap)
    # ------------------------------------------------------------------

    def signed_url(self, key: str, ttl_seconds: int) -> str:
        expires = int(time.time()) + ttl_seconds
        token = self._make_token("GET", key, expires, 0)
        return (
            f"/api/v1/storage/serve?key={urllib.parse.quote(key, safe='')}"
            f"&expires={expires}&token={token}"
        )

    def signed_upload_url(self, key: str, ttl_seconds: int, max_bytes: int) -> str:
        expires = int(time.time()) + ttl_seconds
        token = self._make_token("PUT", key, expires, max_bytes)
        return (
            f"/api/v1/storage/upload?key={urllib.parse.quote(key, safe='')}"
            f"&expires={expires}&max_bytes={max_bytes}&token={token}"
        )

    def verify_token(self, method: str, key: str, expires: int, max_bytes: int, token: str) -> bool:
        """Constant-time verification. False if expired or tampered."""
        if int(time.time()) > expires:
            return False
        expected = self._make_token(method, key, expires, max_bytes)
        return hmac.compare_digest(expected, token)

    def _make_token(self, method: str, key: str, expires: int, max_bytes: int) -> str:
        message = f"{method}:{key}:{expires}:{max_bytes}".encode()
        return hmac.new(
            settings.storage_signing_secret.encode(), message, hashlib.sha256
        ).hexdigest()
