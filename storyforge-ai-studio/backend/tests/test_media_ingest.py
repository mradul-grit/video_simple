from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.storage.local import LocalFilesystemStorage, _safe_path


def _grant(client, headers, pid, size, content_type="video/mp4", name="a.mp4"):
    return client.post(
        f"/api/v1/projects/{pid}/media/upload-url",
        json={"filename": name, "content_type": content_type, "expected_bytes": size},
        headers=headers,
    )


def test_upload_validate_and_probe_metadata(
    client: TestClient, alice, make_project, upload_video, sample_video: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    assert asset["status"] == "ready"
    assert (asset["width"], asset["height"]) == (320, 240)
    assert asset["video_codec"] == "h264"
    assert asset["audio_codec"] == "aac"
    assert asset["has_audio"] is True
    assert 2.8 < asset["duration_seconds"] < 3.3
    assert asset["file_size_bytes"] == sample_video.stat().st_size


def test_storage_key_is_server_chosen_not_user_filename(
    client: TestClient, alice, make_project, sample_video: Path, storage_root: Path
) -> None:
    pid = make_project(alice)
    data = sample_video.read_bytes()
    r = _grant(client, alice, pid, len(data), name="../../evil.mp4")
    assert r.status_code == 201
    assert "evil" not in r.json()["upload_url"]
    client.put(r.json()["upload_url"], content=data)
    stored = [
        p.relative_to(storage_root).as_posix() for p in storage_root.rglob("*") if p.is_file()
    ]
    assert stored == [f"projects/{pid}/media/{r.json()['media_asset_id']}/original"]


def test_declared_size_over_limit_rejected(
    client: TestClient, alice, make_project, monkeypatch
) -> None:
    pid = make_project(alice)
    monkeypatch.setattr(settings, "max_upload_bytes", 1000)
    assert _grant(client, alice, pid, 1001).status_code == 413


def test_unsupported_content_type_rejected(client: TestClient, alice, make_project) -> None:
    pid = make_project(alice)
    r = _grant(client, alice, pid, 100, content_type="application/x-msdownload", name="a.exe")
    assert r.status_code == 422


def test_upload_larger_than_grant_rejected(
    client: TestClient, alice, make_project, sample_video: Path
) -> None:
    pid = make_project(alice)
    data = sample_video.read_bytes()
    grant = _grant(client, alice, pid, 100).json()  # promise 100 bytes, send the whole file
    r = client.put(grant["upload_url"], content=data)
    assert r.status_code == 413


def test_tampered_or_expired_grant_rejected(
    client: TestClient, alice, make_project, sample_video: Path
) -> None:
    pid = make_project(alice)
    data = sample_video.read_bytes()
    grant = _grant(client, alice, pid, len(data)).json()
    url = grant["upload_url"]
    # raise the byte cap without re-signing
    forged = url.replace(f"max_bytes={len(data)}", f"max_bytes={len(data) * 100}")
    assert client.put(forged, content=data).status_code == 403
    # wrong token
    bad = url.rsplit("token=", 1)[0] + "token=" + "0" * 64
    assert client.put(bad, content=data).status_code == 403
    # expired
    storage = LocalFilesystemStorage()
    key = f"projects/{pid}/media/{grant['media_asset_id']}/original"
    old = int(time.time()) - 10
    token = storage._make_token("PUT", key, old, len(data))
    expired = f"/api/v1/storage/upload?key={key}&expires={old}&max_bytes={len(data)}&token={token}"
    assert client.put(expired, content=data).status_code == 403


def test_grant_cannot_be_replayed(
    client: TestClient, alice, make_project, sample_video: Path
) -> None:
    pid = make_project(alice)
    data = sample_video.read_bytes()
    grant = _grant(client, alice, pid, len(data)).json()
    assert client.put(grant["upload_url"], content=data).status_code == 204
    assert client.put(grant["upload_url"], content=data).status_code == 409


def test_complete_before_upload_is_rejected(client: TestClient, alice, make_project) -> None:
    pid = make_project(alice)
    grant = _grant(client, alice, pid, 100).json()
    r = client.post(
        f"/api/v1/projects/{pid}/media/complete",
        json={"media_asset_id": grant["media_asset_id"]},
        headers=alice,
    )
    assert r.status_code == 409


def test_non_video_bytes_fail_validation_and_are_deleted(
    client: TestClient, alice, make_project, storage_root: Path
) -> None:
    pid = make_project(alice)
    junk = b"MZ\x90\x00" + b"not a video at all" * 100
    grant = _grant(client, alice, pid, len(junk)).json()
    assert client.put(grant["upload_url"], content=junk).status_code == 204
    r = client.post(
        f"/api/v1/projects/{pid}/media/complete",
        json={"media_asset_id": grant["media_asset_id"]},
        headers=alice,
    )
    assert r.status_code == 202
    job = client.get(f"/api/v1/jobs/{r.json()['id']}", headers=alice).json()
    assert job["status"] == "failed"
    assert "signature" in job["message"].lower() or "supported" in job["message"].lower()
    asset = client.get(f"/api/v1/projects/{pid}/media", headers=alice).json()[0]
    assert asset["status"] == "failed"
    assert not [p for p in storage_root.rglob("original") if p.is_file()]


def test_truncated_video_fails_validation(
    client: TestClient, alice, make_project, sample_video: Path
) -> None:
    pid = make_project(alice)
    data = sample_video.read_bytes()[:64]  # valid ftyp header, no usable streams
    grant = _grant(client, alice, pid, len(data)).json()
    client.put(grant["upload_url"], content=data)
    r = client.post(
        f"/api/v1/projects/{pid}/media/complete",
        json={"media_asset_id": grant["media_asset_id"]},
        headers=alice,
    )
    job = client.get(f"/api/v1/jobs/{r.json()['id']}", headers=alice).json()
    assert job["status"] == "failed"


def test_overlong_video_rejected(
    client: TestClient, alice, make_project, upload_video, sample_video: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "max_video_duration_seconds", 1)
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    assert asset["status"] == "failed"


def test_complete_is_idempotent(
    client: TestClient, alice, make_project, sample_video: Path
) -> None:
    pid = make_project(alice)
    data = sample_video.read_bytes()
    grant = _grant(client, alice, pid, len(data)).json()
    client.put(grant["upload_url"], content=data)
    body = {"media_asset_id": grant["media_asset_id"]}
    a = client.post(f"/api/v1/projects/{pid}/media/complete", json=body, headers=alice)
    b = client.post(f"/api/v1/projects/{pid}/media/complete", json=body, headers=alice)
    assert a.json()["id"] == b.json()["id"]


def test_media_is_private_between_users(
    client: TestClient, alice, bob, make_project, upload_video, sample_video: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    bob_pid = make_project(bob)
    # Bob cannot use Alice's project, nor address her asset through his own project.
    assert client.get(f"/api/v1/projects/{pid}/media", headers=bob).status_code == 404
    assert (
        client.delete(f"/api/v1/projects/{bob_pid}/media/{asset['id']}", headers=bob).status_code
        == 404
    )
    r = client.post(
        f"/api/v1/projects/{bob_pid}/media/complete",
        json={"media_asset_id": asset["id"]},
        headers=bob,
    )
    assert r.status_code == 404


def test_delete_media_removes_object(
    client: TestClient, alice, make_project, upload_video, sample_video: Path, storage_root: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    assert (
        client.delete(f"/api/v1/projects/{pid}/media/{asset['id']}", headers=alice).status_code
        == 204
    )
    assert client.get(f"/api/v1/projects/{pid}/media", headers=alice).json() == []
    assert not [p for p in storage_root.rglob("*") if p.is_file()]


def test_delete_project_purges_objects_and_rows(
    client: TestClient,
    alice,
    make_project,
    upload_video,
    sample_video: Path,
    storage_root: Path,
    session_factory,
) -> None:
    from app.db.models import Job, MediaAsset, Project

    pid = make_project(alice)
    upload_video(alice, pid, sample_video)
    assert [p for p in storage_root.rglob("*") if p.is_file()]
    assert client.delete(f"/api/v1/projects/{pid}", headers=alice).status_code == 204
    assert not [p for p in storage_root.rglob("*") if p.is_file()]
    with session_factory() as db:
        assert db.query(Project).count() == 0
        assert db.query(MediaAsset).count() == 0
        assert db.query(Job).count() == 0
    assert client.get(f"/api/v1/projects/{pid}", headers=alice).status_code == 404


def test_signed_download_roundtrip_and_expiry(storage_root: Path, client: TestClient) -> None:
    storage = LocalFilesystemStorage()
    storage.put_object("projects/p/x.bin", b"hello")
    url = storage.signed_url("projects/p/x.bin", 60)
    r = client.get(url)
    assert r.status_code == 200 and r.content == b"hello"
    assert r.headers["cache-control"] == "private, no-store"
    assert client.get(url.rsplit("token=", 1)[0] + "token=deadbeef").status_code == 403
    assert client.get(storage.signed_url("projects/p/x.bin", -5)).status_code == 403


@pytest.mark.parametrize(
    "key", ["../outside", "projects/../../outside", "/etc/passwd", "..\\..\\outside"]
)
def test_path_traversal_is_blocked(storage_root: Path, key: str) -> None:
    storage_root.mkdir(parents=True, exist_ok=True)
    resolved = (
        _safe_path(storage_root, key) if not key.startswith("..") and ".." not in key else None
    )
    if ".." in key:
        with pytest.raises(ValueError):
            _safe_path(storage_root, key)
    else:  # absolute-looking keys are re-rooted inside storage, never the real filesystem path
        assert storage_root.resolve() in resolved.parents


def test_media_preview_url_owner_only(
    client: TestClient, alice, bob, make_project, upload_video, sample_video: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    url = f"/api/v1/projects/{pid}/media/{asset['id']}/preview-url"
    r = client.post(url, headers=alice)
    assert r.status_code == 200
    got = client.get(r.json()["url"])
    assert got.status_code == 200 and got.content == sample_video.read_bytes()
    assert client.post(url, headers=bob).status_code == 404
