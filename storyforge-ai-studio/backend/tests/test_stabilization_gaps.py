"""Gap coverage for the stabilization fixes: cancel guards in every worker, validation retry,
and each rate-limited endpoint."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.ratelimit import LIMITS


def _grant_and_put(client, headers, pid, video: Path) -> dict:
    data = video.read_bytes()
    g = client.post(
        f"/api/v1/projects/{pid}/media/upload-url",
        json={"filename": "v.mp4", "content_type": "video/mp4", "expected_bytes": len(data)},
        headers=headers,
    ).json()
    assert client.put(g["upload_url"], content=data).status_code == 204
    return g


def _complete(client, headers, pid, media_id) -> dict:
    r = client.post(
        f"/api/v1/projects/{pid}/media/complete", json={"media_asset_id": media_id}, headers=headers
    )
    assert r.status_code == 202, r.text
    return r.json()


def _media_status(client, headers, pid) -> str:
    return client.get(f"/api/v1/projects/{pid}/media", headers=headers).json()[0]["status"]


def _job(client, headers, job_id) -> dict:
    return client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()


def _cancel_job_elsewhere(session_factory, job_id: str) -> None:
    """Simulate the user cancelling from another request while the worker is busy."""
    from app.db.models import Job, JobStatus

    with session_factory() as other:
        other.get(Job, job_id).status = JobStatus.cancelled
        other.commit()


# --- media validation -------------------------------------------------------------------


def test_validation_cancelled_before_start_leaves_upload_untouched(
    client: TestClient, alice, make_project, sample_video: Path, monkeypatch
) -> None:
    from app.workers import tasks

    pid = make_project(alice)
    g = _grant_and_put(client, alice, pid, sample_video)
    monkeypatch.setattr(tasks.run_media_validation, "apply_async", lambda *a, **k: None)
    job = _complete(client, alice, pid, g["media_asset_id"])
    client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=alice)

    tasks.run_media_validation.run(job["id"], g["media_asset_id"])  # worker arrives late
    assert _job(client, alice, job["id"])["status"] == "cancelled"
    assert _media_status(client, alice, pid) == "uploaded"  # not validated, not deleted


def test_validation_cancelled_midway_is_not_marked_ready(
    client: TestClient,
    alice,
    make_project,
    sample_video: Path,
    monkeypatch,
    session_factory,
    storage_root: Path,
) -> None:
    import app.services.ingest as ingest

    pid = make_project(alice)
    g = _grant_and_put(client, alice, pid, sample_video)
    real_probe = ingest.probe

    def probe_then_cancel(path, timeout=60):
        meta = real_probe(path, timeout=timeout)
        from app.db.models import Job

        with session_factory() as other:
            job_id = other.query(Job.id).filter(Job.media_asset_id == g["media_asset_id"]).scalar()
        _cancel_job_elsewhere(session_factory, job_id)
        return meta

    monkeypatch.setattr(ingest, "probe", probe_then_cancel)
    job = _complete(client, alice, pid, g["media_asset_id"])
    assert _job(client, alice, job["id"])["status"] == "cancelled"
    assert _media_status(client, alice, pid) == "uploaded"
    assert [p for p in storage_root.rglob("original") if p.is_file()], "upload must be kept"


def test_cancelled_validation_can_be_started_again(
    client: TestClient, alice, make_project, sample_video: Path, monkeypatch
) -> None:
    """Regression: once cancel became final, /complete returned the cancelled job forever."""
    from app.workers import tasks

    pid = make_project(alice)
    g = _grant_and_put(client, alice, pid, sample_video)
    real = tasks.run_media_validation.apply_async
    monkeypatch.setattr(tasks.run_media_validation, "apply_async", lambda *a, **k: None)
    job = _complete(client, alice, pid, g["media_asset_id"])
    client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=alice)

    monkeypatch.setattr(tasks.run_media_validation, "apply_async", real)
    again = _complete(client, alice, pid, g["media_asset_id"])
    assert again["id"] == job["id"]  # same logical job
    done = _job(client, alice, job["id"])
    assert done["status"] == "completed"
    assert _media_status(client, alice, pid) == "ready"


def test_validation_retry_after_probe_timeout(
    client: TestClient, alice, bob, make_project, sample_video: Path, monkeypatch
) -> None:
    import app.services.ingest as ingest
    from app.media.probe import MediaProbeTimeout

    real_probe = ingest.probe
    monkeypatch.setattr(
        ingest, "probe", lambda p, timeout=60: (_ for _ in ()).throw(MediaProbeTimeout("slow"))
    )
    pid = make_project(alice)
    g = _grant_and_put(client, alice, pid, sample_video)
    job = _complete(client, alice, pid, g["media_asset_id"])
    failed = _job(client, alice, job["id"])
    assert failed["status"] == "failed" and failed["retryable"] is True

    assert client.post(f"/api/v1/jobs/{job['id']}/retry", headers=bob).status_code == 404
    monkeypatch.setattr(ingest, "probe", real_probe)
    r = client.post(f"/api/v1/jobs/{job['id']}/retry", headers=alice)
    assert r.status_code == 202, r.text
    assert _job(client, alice, job["id"])["status"] == "completed"
    assert _media_status(client, alice, pid) == "ready"


# --- visual search ------------------------------------------------------------------------


@pytest.fixture()
def analysed(
    client: TestClient, alice, make_project, upload_video, paused_video: Path, monkeypatch
):
    from app.workers import tasks

    pid = make_project(alice)
    upload_video(alice, pid, paused_video)
    client.post(f"/api/v1/projects/{pid}/analysis", json={"idempotency_key": "a"}, headers=alice)
    beats = client.get(f"/api/v1/projects/{pid}/analysis", headers=alice).json()["story_beats"]
    assert beats
    fake = [
        {"provider": "openverse", "source_url": "https://example.org/x", "license_spdx": "CC0-1.0"}
    ]
    monkeypatch.setattr(
        tasks, "_search_visuals", lambda beat, settings: [dict(f) for f in fake]
    )  # no network
    return pid, [b["id"] for b in beats]


def _enqueue_visual(client, headers, pid, beat_ids, key="v"):
    return client.post(
        f"/api/v1/projects/{pid}/visual-suggestions",
        json={"story_beat_ids": beat_ids, "idempotency_key": key},
        headers=headers,
    )


def test_visual_search_works_and_cancel_before_start_is_final(
    client: TestClient, alice, analysed, monkeypatch
) -> None:
    from app.workers import tasks

    pid, beats = analysed
    assert _enqueue_visual(client, alice, pid, beats, "ok").status_code == 202
    assert len(
        client.get(f"/api/v1/projects/{pid}/visual-suggestions", headers=alice).json()
    ) == len(beats)

    monkeypatch.setattr(tasks.run_visual_search, "apply_async", lambda *a, **k: None)
    job = _enqueue_visual(client, alice, pid, beats, "late").json()
    client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=alice)
    assert tasks.run_visual_search.run(job["id"], pid, beats)["status"] == "cancelled"
    assert _job(client, alice, job["id"])["status"] == "cancelled"
    assert len(
        client.get(f"/api/v1/projects/{pid}/visual-suggestions", headers=alice).json()
    ) == len(beats)


def test_visual_search_cancelled_midway_saves_nothing(
    client: TestClient, alice, analysed, monkeypatch, session_factory
) -> None:
    from app.db.models import Job
    from app.workers import tasks

    pid, beats = analysed

    def search_then_cancel(beat, settings):
        with session_factory() as other:
            job_id = other.query(Job.id).filter(Job.idempotency_key == "mid").scalar()
        _cancel_job_elsewhere(session_factory, job_id)
        return [{"provider": "openverse", "source_url": "https://example.org/y"}]

    monkeypatch.setattr(tasks, "_search_visuals", search_then_cancel)
    job = _enqueue_visual(client, alice, pid, beats, "mid").json()
    assert _job(client, alice, job["id"])["status"] == "cancelled"
    assert client.get(f"/api/v1/projects/{pid}/visual-suggestions", headers=alice).json() == []


# --- render start ---------------------------------------------------------------------------


def test_render_cancelled_before_start_never_runs(
    client: TestClient,
    alice,
    make_project,
    upload_video,
    sample_video: Path,
    monkeypatch,
    session_factory,
    storage_root,
) -> None:
    from app.db.models import JobStatus, RenderJob
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
                        "end": 1.0,
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
    monkeypatch.setattr(tasks.run_render, "apply_async", lambda *a, **k: None)
    rj = client.post(
        f"/api/v1/projects/{pid}/renders",
        json={"manifest_version": saved["version"], "preset": "preview"},
        headers=alice,
    ).json()
    with session_factory() as other:
        other.get(RenderJob, rj["id"]).status = JobStatus.cancelled
        other.commit()

    out = tasks.run_render.run(rj["id"], pid, saved["id"], "preview")
    assert out["status"] == "cancelled"
    final = client.get(f"/api/v1/renders/{rj['id']}", headers=alice).json()
    assert final["status"] == "cancelled" and final["output_size_bytes"] is None
    assert not list(storage_root.rglob("output.mp4"))
    assert client.post(f"/api/v1/exports/{rj['id']}/download-url", headers=alice).status_code == 409


# --- rate limits ------------------------------------------------------------------------------


def _assert_limited(responses, limit: int) -> None:
    codes = [r.status_code for r in responses]
    assert 429 not in codes[:limit], codes
    last = responses[limit]
    assert last.status_code == 429, codes
    body = last.json()
    assert body["error"]["code"] == "RATE_LIMITED" and body["error"]["retryable"] is True
    assert int(last.headers["Retry-After"]) > 0


def test_dev_login_is_limited_per_ip(client: TestClient) -> None:
    from app.api import ratelimit

    limit = LIMITS["auth:dev-login"][0]
    rs = [
        client.post("/api/v1/auth/dev-login", json={"email": f"u{i}@example.com"})
        for i in range(limit + 1)
    ]
    _assert_limited(rs, limit)
    ratelimit._check("auth:dev-login", "198.51.100.7")  # a different address is not affected


@pytest.mark.parametrize(
    ("name", "method", "path", "body"),
    [
        ("media:upload-url", "post", "/api/v1/projects/{pid}/media/upload-url", {}),
        ("analysis:enqueue", "post", "/api/v1/projects/{pid}/analysis", {"idempotency_key": "k"}),
        ("visual:enqueue", "post", "/api/v1/projects/{pid}/visual-suggestions", {}),
        ("renders:enqueue", "post", "/api/v1/projects/{pid}/renders", {}),
        ("jobs:retry", "post", "/api/v1/jobs/{missing}/retry", None),
    ],
)
def test_endpoint_rate_limits(
    client: TestClient, alice, bob, make_project, name, method, path, body
) -> None:
    """Cheap failing requests still count: the limit is checked before any work is done."""
    pid = make_project(alice)
    url = path.format(pid=pid, missing=uuid.uuid4())
    limit = LIMITS[name][0]
    send = getattr(client, method)
    rs = [
        send(url, json=body, headers=alice) if body is not None else send(url, headers=alice)
        for _ in range(limit + 1)
    ]
    _assert_limited(rs, limit)
    other = send(
        path.format(pid=make_project(bob), missing=uuid.uuid4()),
        headers=bob,
        **({"json": body} if body is not None else {}),
    )
    assert other.status_code != 429  # limits are per user
