"""Deleting a project while it renders must never leave exported media behind (SECURITY_PRIVACY.md).

The worker task runs directly so the real DELETE endpoint can be called at each point of the
render: during ffmpeg, after verification, after the file is stored but before it is published.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def queued_render(
    client: TestClient, alice, make_project, upload_video, sample_video: Path, monkeypatch
):
    from app.workers import tasks

    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    manifest = {
        "schema_version": "1.0",
        "project_id": pid,
        "version": 1,
        "output": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "container": "mp4",
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        "tracks": [
            {
                "id": str(uuid.uuid4()),
                "type": "video",
                "items": [
                    {
                        "id": str(uuid.uuid4()),
                        "source_media_id": asset["id"],
                        "start": 0.0,
                        "end": 2.0,
                    }
                ],
            }
        ],
    }
    saved = client.put(
        f"/api/v1/projects/{pid}/edit-manifest",
        json={"expected_version": 0, "manifest_json": manifest},
        headers=alice,
    ).json()
    monkeypatch.setattr(
        tasks.run_render, "apply_async", lambda *a, **k: None
    )  # we run the worker ourselves
    rj = client.post(
        f"/api/v1/projects/{pid}/renders",
        json={"manifest_version": saved["version"], "preset": "preview"},
        headers=alice,
    ).json()
    return pid, rj["id"], saved["id"]


def _run(pid, render_id, manifest_id) -> dict:
    from app.workers import tasks

    return tasks.run_render.run(render_id, pid, manifest_id, "preview")  # must never raise


def _files(root: Path) -> list[str]:
    return (
        [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
        if root.exists()
        else []
    )


def _render_rows(session_factory) -> int:
    from app.db.models import RenderJob

    with session_factory() as db:
        return db.query(RenderJob).count()


def test_delete_during_ffmpeg(
    client, alice, queued_render, monkeypatch, storage_root, session_factory
) -> None:
    import app.services.renderer as renderer

    pid, rid, mid = queued_render
    real = renderer.render_manifest

    def wrapped(**kw):
        cb = kw["progress_callback"]

        def progress(pct, stage):
            if stage == "rendering":
                assert client.delete(f"/api/v1/projects/{pid}", headers=alice).status_code == 204
            cb(pct, stage)

        return real(**{**kw, "progress_callback": progress})

    monkeypatch.setattr(renderer, "render_manifest", wrapped)
    assert _run(pid, rid, mid)["status"] == "cancelled"
    assert _files(storage_root) == []
    assert _render_rows(session_factory) == 0


def test_delete_after_verification_before_store(
    client, alice, queued_render, monkeypatch, storage_root, session_factory
) -> None:
    """Regression: this window used to leave an orphaned output.mp4 after the purge."""
    import app.services.renderer as renderer

    pid, rid, mid = queued_render
    real = renderer.render_manifest

    def wrapped(**kw):
        out = real(**kw)
        assert client.delete(f"/api/v1/projects/{pid}", headers=alice).status_code == 204
        return out

    monkeypatch.setattr(renderer, "render_manifest", wrapped)
    assert _run(pid, rid, mid)["status"] == "cancelled"
    assert _files(storage_root) == []
    assert _render_rows(session_factory) == 0


def test_deletion_started_after_store_before_publish(
    client, alice, queued_render, monkeypatch, storage_root, session_factory
) -> None:
    """Project marked deleting, purge not yet run: the worker must remove its own file."""
    from app.db.models import Project, ProjectStatus
    from app.storage.local import LocalFilesystemStorage

    pid, rid, mid = queued_render
    real_put = LocalFilesystemStorage.put_file

    def put_then_start_deletion(self, key, source):
        real_put(self, key, source)
        with session_factory() as db:
            db.get(Project, pid).status = ProjectStatus.deleting
            db.commit()

    monkeypatch.setattr(LocalFilesystemStorage, "put_file", put_then_start_deletion)
    assert _run(pid, rid, mid)["status"] == "cancelled"
    assert not [f for f in _files(storage_root) if f.endswith("output.mp4")]
    final = client.get(f"/api/v1/renders/{rid}", headers=alice).json()
    assert final["status"] != "completed" and final["output_size_bytes"] is None


def test_render_cancelled_mid_run_is_never_published(
    client, alice, queued_render, monkeypatch, storage_root, session_factory
) -> None:
    import app.services.renderer as renderer
    from app.db.models import JobStatus, RenderJob

    pid, rid, mid = queued_render
    real = renderer.render_manifest

    def wrapped(**kw):
        out = real(**kw)
        with session_factory() as db:
            db.get(RenderJob, rid).status = JobStatus.cancelled
            db.commit()
        return out

    monkeypatch.setattr(renderer, "render_manifest", wrapped)
    assert _run(pid, rid, mid)["status"] == "cancelled"
    job = client.get(f"/api/v1/renders/{rid}", headers=alice).json()
    assert job["status"] == "cancelled" and job["output_size_bytes"] is None
    assert not [f for f in _files(storage_root) if f.endswith("output.mp4")]


def test_crash_after_deletion_is_handled(
    client, alice, queued_render, monkeypatch, storage_root
) -> None:
    import app.services.renderer as renderer

    pid, rid, mid = queued_render

    def delete_then_crash(**kw):
        assert client.delete(f"/api/v1/projects/{pid}", headers=alice).status_code == 204
        raise RuntimeError("ffmpeg segfault")

    monkeypatch.setattr(renderer, "render_manifest", delete_then_crash)
    assert _run(pid, rid, mid)["status"] == "failed"  # logged, not raised (no ObjectDeletedError)
    assert _files(storage_root) == []


def test_normal_render_still_publishes(client, alice, queued_render, storage_root) -> None:
    pid, rid, mid = queued_render
    assert _run(pid, rid, mid)["status"] == "completed"
    job = client.get(f"/api/v1/renders/{rid}", headers=alice).json()
    assert job["status"] == "completed" and job["output_size_bytes"] > 0
    assert [f for f in _files(storage_root) if f.endswith("output.mp4")]
