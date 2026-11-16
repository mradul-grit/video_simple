from __future__ import annotations

import copy
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ready_project(client: TestClient, alice, make_project, upload_video, sample_video: Path):
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    assert asset["status"] == "ready"
    return pid, asset


def _analyse(client, headers, pid, key="k1"):
    return client.post(
        f"/api/v1/projects/{pid}/analysis", json={"idempotency_key": key}, headers=headers
    )


def _result(client, headers, pid):
    return client.get(f"/api/v1/projects/{pid}/analysis", headers=headers).json()


def test_analysis_requires_a_ready_media_asset(client: TestClient, alice, make_project) -> None:
    pid = make_project(alice)
    assert _analyse(client, alice, pid).status_code == 422


def test_analysis_produces_grounded_results_and_labels_demo_output(
    client: TestClient, alice, ready_project
) -> None:
    pid, _ = ready_project
    r = _analyse(client, alice, pid)
    assert r.status_code == 202
    assert (
        client.get(f"/api/v1/jobs/{r.json()['id']}", headers=alice).json()["status"] == "completed"
    )

    res = _result(client, alice, pid)
    seg_ids = {s["id"] for s in res["transcript_segments"]}
    assert seg_ids
    # Mock provider output must be visibly labelled, never passed off as real.
    spoken = [s for s in res["transcript_segments"] if s["is_speech"]]
    assert all(s["text"].startswith("[DEMO]") for s in spoken)
    assert res["story_beats"]
    for cap in res["editorial_captions"]:
        assert cap["text"].startswith("[DEMO CAPTION]")
        assert cap["transcript_segment_ids"], "editorial captions must cite transcript segments"
        assert set(cap["transcript_segment_ids"]) <= seg_ids
    for beat in res["story_beats"]:
        assert set(beat["transcript_segment_ids"]) <= seg_ids
    for cut in res["cut_proposals"]:
        assert cut["accepted"] is None  # nothing is applied without user review
        assert cut["end_seconds"] > cut["start_seconds"]


def test_analysis_is_idempotent(client: TestClient, alice, ready_project) -> None:
    pid, _ = ready_project
    a = _analyse(client, alice, pid, "same")
    first = _result(client, alice, pid)
    b = _analyse(client, alice, pid, "same")
    assert a.json()["id"] == b.json()["id"]
    second = _result(client, alice, pid)
    assert [s["id"] for s in first["transcript_segments"]] == [
        s["id"] for s in second["transcript_segments"]
    ]


def test_cut_review_accept_reject_adjust(client: TestClient, alice, ready_project) -> None:
    pid, _ = ready_project
    _analyse(client, alice, pid)
    cuts = _result(client, alice, pid)["cut_proposals"]
    assert cuts
    cut = cuts[0]
    r = client.patch(
        f"/api/v1/projects/{pid}/cuts/{cut['id']}",
        json={"accepted": True, "start_seconds": cut["start_seconds"] + 0.1},
        headers=alice,
    )
    assert r.status_code == 200
    assert r.json()["accepted"] is True
    assert r.json()["start_seconds"] == pytest.approx(cut["start_seconds"] + 0.1)
    r = client.patch(
        f"/api/v1/projects/{pid}/cuts/{cut['id']}", json={"accepted": False}, headers=alice
    )
    assert r.json()["accepted"] is False


def test_cut_review_rejects_invalid_range(client: TestClient, alice, ready_project) -> None:
    pid, _ = ready_project
    _analyse(client, alice, pid)
    cut = _result(client, alice, pid)["cut_proposals"][0]
    r = client.patch(
        f"/api/v1/projects/{pid}/cuts/{cut['id']}",
        json={"accepted": True, "start_seconds": 5.0, "end_seconds": 4.0},
        headers=alice,
    )
    assert r.status_code == 422


def test_cut_review_is_private(client: TestClient, alice, bob, ready_project) -> None:
    pid, _ = ready_project
    _analyse(client, alice, pid)
    cut = _result(client, alice, pid)["cut_proposals"][0]
    r = client.patch(
        f"/api/v1/projects/{pid}/cuts/{cut['id']}", json={"accepted": True}, headers=bob
    )
    assert r.status_code == 404


# --------------------------- edit manifest -------------------------------


def _manifest(pid: str, media_id: str, **video_item) -> dict:
    item = {"id": str(uuid.uuid4()), "source_media_id": media_id, "start": 0.0, "end": 2.0}
    item.update(video_item)
    return {
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
            "quality_preset": "preview",
        },
        "tracks": [{"id": str(uuid.uuid4()), "type": "video", "items": [item]}],
    }


def _save(client, headers, pid, manifest, expected=0):
    return client.put(
        f"/api/v1/projects/{pid}/edit-manifest",
        json={"expected_version": expected, "manifest_json": manifest},
        headers=headers,
    )


def test_manifest_save_versioning_and_conflict(client: TestClient, alice, ready_project) -> None:
    pid, asset = ready_project
    m = _manifest(pid, asset["id"])
    first = _save(client, alice, pid, m, 0)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    second = _save(client, alice, pid, m, 1)
    assert second.json()["version"] == 2
    stale = _save(client, alice, pid, m, 1)  # someone already saved v2
    assert stale.status_code == 409
    assert client.get(f"/api/v1/projects/{pid}/edit-manifest", headers=alice).json()["version"] == 2


def test_manifest_schema_violations_rejected(client: TestClient, alice, ready_project) -> None:
    pid, asset = ready_project
    bad = _manifest(pid, asset["id"])
    bad["output"]["width"] = 720  # schema pins 1080x1920
    r = _save(client, alice, pid, bad)
    assert r.status_code == 422
    assert any("width" in e for e in r.json()["detail"]["errors"])
    extra = _manifest(pid, asset["id"])
    extra["surprise"] = True  # additionalProperties: false
    assert _save(client, alice, pid, extra).status_code == 422


@pytest.mark.parametrize(
    ("patch", "needle"),
    [
        ({"end": 99.0}, "past the source duration"),
        ({"start": 1.5, "end": 1.0}, "start < end"),
        ({"source_media_id": str(uuid.uuid4())}, "not a ready media asset"),
    ],
)
def test_manifest_semantic_video_rules(
    client: TestClient, alice, ready_project, patch, needle
) -> None:
    pid, asset = ready_project
    r = _save(client, alice, pid, _manifest(pid, asset["id"], **patch))
    assert r.status_code == 422, r.text
    assert any(needle in e for e in r.json()["detail"]["errors"]), r.json()


def test_manifest_overlapping_cuts_rejected(client: TestClient, alice, ready_project) -> None:
    pid, asset = ready_project
    m = _manifest(pid, asset["id"], start=0.0, end=2.0)
    m["tracks"][0]["items"].append(
        {"id": str(uuid.uuid4()), "source_media_id": asset["id"], "start": 1.0, "end": 2.5}
    )
    r = _save(client, alice, pid, m)
    assert r.status_code == 422
    assert any("overlap" in e for e in r.json()["detail"]["errors"])


def test_manifest_project_id_must_match(client: TestClient, alice, ready_project) -> None:
    pid, asset = ready_project
    r = _save(client, alice, pid, _manifest(str(uuid.uuid4()), asset["id"]))
    assert r.status_code == 422


def test_editorial_caption_must_cite_real_transcript_segments(
    client: TestClient, alice, ready_project
) -> None:
    pid, asset = ready_project
    _analyse(client, alice, pid)
    seg_id = _result(client, alice, pid)["transcript_segments"][0]["id"]

    def with_caption(ids):
        m = _manifest(pid, asset["id"])
        m["tracks"].append(
            {
                "id": str(uuid.uuid4()),
                "type": "editorial_caption",
                "items": [
                    {
                        "id": str(uuid.uuid4()),
                        "start": 0.0,
                        "end": 1.0,
                        "text": "Key point",
                        "source_segment_ids": ids,
                    }
                ],
            }
        )
        return m

    assert _save(client, alice, pid, with_caption([seg_id])).status_code == 200
    assert _save(client, alice, pid, with_caption([]), 1).status_code == 422
    assert _save(client, alice, pid, with_caption([str(uuid.uuid4())]), 1).status_code == 422


def test_validate_endpoint_does_not_persist(client: TestClient, alice, ready_project) -> None:
    pid, asset = ready_project
    body = {"expected_version": 0, "manifest_json": _manifest(pid, asset["id"])}
    r = client.post(f"/api/v1/projects/{pid}/edit-manifest/validate", json=body, headers=alice)
    assert r.json() == {"valid": True, "errors": []}
    assert client.get(f"/api/v1/projects/{pid}/edit-manifest", headers=alice).status_code == 404


def test_manifest_is_private(client: TestClient, alice, bob, ready_project) -> None:
    pid, asset = ready_project
    assert _save(client, bob, pid, _manifest(pid, asset["id"])).status_code == 404


def test_manifest_save_does_not_mutate_caller_payload(
    client: TestClient, alice, ready_project
) -> None:
    pid, asset = ready_project
    m = _manifest(pid, asset["id"])
    snapshot = copy.deepcopy(m)
    _save(client, alice, pid, m)
    assert m == snapshot
