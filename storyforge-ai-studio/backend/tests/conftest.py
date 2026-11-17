"""Shared fixtures.

API tests run against an in-memory SQLite database and a temp storage directory.
Celery runs eagerly so worker tasks execute for real (mock AI providers, real
ffmpeg/ffprobe). Nothing here needs Postgres, Redis or network access.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.base as db_base
import app.db.models  # noqa: F401  (register tables)
from app.api import ratelimit
from app.config import settings
from app.db.base import Base, get_db
from app.main import app
from app.workers.celery_app import celery_app


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real 3 s 320x240 H.264/AAC clip generated with ffmpeg."""
    if shutil.which("ffmpeg") is None:
        pytest.fail("ffmpeg is required for these tests (see README prerequisites)")
    out = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=3:size=320x240:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ],
        check=True,
    )
    return out


@pytest.fixture(scope="session")
def paused_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """4 s clip whose audio is silent from 1.5 s to 2.8 s (a real, measurable pause)."""
    out = tmp_path_factory.mktemp("media_paused") / "paused.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-af", "volume='if(between(t,1.5,2.8),0,1)':eval=frame",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out),
        ],
        check=True,
    )  # fmt: skip
    return out


@pytest.fixture(scope="session")
def silent_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 2 s clip with no audio stream (must still render)."""
    out = tmp_path_factory.mktemp("media_silent") / "silent.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=320x240:rate=25",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out


@pytest.fixture()
def session_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    # Default: in-memory SQLite. Set TEST_DATABASE_URL to run the same suite on PostgreSQL
    # (use a throwaway database: tables are dropped before and after every test).
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    # Workers open their own sessions through app.db.base.SessionLocal.
    monkeypatch.setattr(db_base, "SessionLocal", factory)
    yield factory
    if url:
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "storage"
    monkeypatch.setattr(settings, "local_storage_root", str(root))
    return root


@pytest.fixture()
def client(
    session_factory: sessionmaker[Session],
    storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # In-memory rate limiter, fresh for every test (never the real Redis).
    monkeypatch.setattr(settings, "rate_limit_backend", "memory")
    ratelimit.reset_store()
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", False)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def alice(client: TestClient) -> dict[str, str]:
    return _login(client, "alice@example.com")


@pytest.fixture()
def bob(client: TestClient) -> dict[str, str]:
    return _login(client, "bob@example.com")


@pytest.fixture()
def make_project(client: TestClient) -> Callable[..., str]:
    def _make(headers: dict[str, str], title: str = "Test project") -> str:
        r = client.post("/api/v1/projects", json={"title": title}, headers=headers)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return _make


@pytest.fixture()
def upload_video(client: TestClient) -> Callable[..., dict]:
    """Run the full upload flow; returns the media asset JSON after validation."""

    def _upload(
        headers: dict[str, str],
        project_id: str,
        path: Path,
        content_type: str = "video/mp4",
    ) -> dict:
        data = path.read_bytes()
        r = client.post(
            f"/api/v1/projects/{project_id}/media/upload-url",
            json={
                "filename": path.name,
                "content_type": content_type,
                "expected_bytes": len(data),
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        grant = r.json()
        put = client.put(grant["upload_url"], content=data)
        assert put.status_code == 204, put.text
        done = client.post(
            f"/api/v1/projects/{project_id}/media/complete",
            json={"media_asset_id": grant["media_asset_id"]},
            headers=headers,
        )
        assert done.status_code == 202, done.text
        listing = client.get(f"/api/v1/projects/{project_id}/media", headers=headers).json()
        return next(a for a in listing if a["id"] == grant["media_asset_id"])

    return _upload


@pytest.fixture()
def new_id() -> Callable[[], str]:
    return lambda: str(uuid.uuid4())
