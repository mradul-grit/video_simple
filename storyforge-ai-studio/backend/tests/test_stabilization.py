"""Regression tests for the seven failure probes recorded in PROJECT_AUDIT_AND_ROADMAP.md."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.timeline import bound_items


@pytest.fixture()
def short_project(client: TestClient, alice, make_project, upload_video, paused_video: Path):
    """4 s clip with a real pause at 1.5-2.8 s."""
    pid = make_project(alice)
    asset = upload_video(alice, pid, paused_video)
    assert asset["status"] == "ready"
    return pid, asset


def _analyse(client, headers, pid, key):
    r = client.post(
        f"/api/v1/projects/{pid}/analysis", json={"idempotency_key": key}, headers=headers
    )
    assert r.status_code == 202, r.text
    return r.json()


def _result(client, headers, pid):
    return client.get(f"/api/v1/projects/{pid}/analysis", headers=headers).json()


# --- probes 1 & 2: transcript and captions inside the video -------------------------


def test_analysis_items_stay_inside_the_video(client: TestClient, alice, short_project) -> None:
    pid, asset = short_project
    duration = asset["duration_seconds"]
    _analyse(client, alice, pid, "k")
    res = _result(client, alice, pid)
    for kind in ("transcript_segments", "editorial_captions", "story_beats", "cut_proposals"):
        assert res[kind], f"expected some {kind}"
        for item in res[kind]:
            assert 0 <= item["start_seconds"] < item["end_seconds"] <= duration + 1e-6, (kind, item)


def test_bound_items_clamps_and_drops() -> None:
    items = [
        {"start_seconds": -1.0, "end_seconds": 2.0},  # clamped to 0
        {"start_seconds": 3.0, "end_seconds": 9.0},  # clamped to 4
        {"start_seconds": 4.0, "end_seconds": 6.0},  # starts at the end: dropped
        {"start_seconds": 2.0, "end_seconds": 2.01},  # too short: dropped
        {"start_seconds": 3.0, "end_seconds": 1.0},  # inverted: dropped
        {"start_seconds": "x", "end_seconds": 1.0},  # malformed: dropped
    ]
    out = bound_items(items, 4.0)
    assert [(i["start_seconds"], i["end_seconds"]) for i in out] == [(0.0, 2.0), (3.0, 4.0)]
    assert items[0]["start_seconds"] == -1.0  # inputs untouched
    assert len(bound_items(items[:2], None)) == 2  # unknown duration: only range sanity


# --- probe 3: re-analysis keeps user decisions ---------------------------------------


def test_reanalysis_keeps_reviewed_cuts_and_stable_ids(
    client: TestClient, alice, short_project
) -> None:
    pid, _ = short_project
    _analyse(client, alice, pid, "first")
    first = _result(client, alice, pid)
    cut = first["cut_proposals"][0]
    adjusted_start = cut["start_seconds"] + 0.05
    r = client.patch(
        f"/api/v1/projects/{pid}/cuts/{cut['id']}",
        json={"accepted": True, "start_seconds": adjusted_start},
        headers=alice,
    )
    assert r.status_code == 200

    _analyse(client, alice, pid, "second")
    second = _result(client, alice, pid)
    kept = [c for c in second["cut_proposals"] if c["id"] == cut["id"]]
    assert kept, "accepted cut was deleted by re-analysis"
    assert kept[0]["accepted"] is True
    assert kept[0]["start_seconds"] == pytest.approx(adjusted_start)  # user's bounds survive
    assert len(second["cut_proposals"]) == 1  # no duplicate of the same pause
    # Same speech -> same segment ids, so captions and manifests keep valid citations.
    assert [s["id"] for s in first["transcript_segments"]] == [
        s["id"] for s in second["transcript_segments"]
    ]


def test_reanalysis_keeps_rejected_cut(client: TestClient, alice, short_project) -> None:
    pid, _ = short_project
    _analyse(client, alice, pid, "a")
    cut = _result(client, alice, pid)["cut_proposals"][0]
    client.patch(
        f"/api/v1/projects/{pid}/cuts/{cut['id']}", json={"accepted": False}, headers=alice
    )
    _analyse(client, alice, pid, "b")
    cuts = _result(client, alice, pid)["cut_proposals"]
    assert [(c["id"], c["accepted"]) for c in cuts] == [(cut["id"], False)]


def test_reanalysis_updates_unreviewed_cut_in_place(
    client: TestClient, alice, short_project
) -> None:
    pid, _ = short_project
    _analyse(client, alice, pid, "a")
    before = _result(client, alice, pid)["cut_proposals"]
    _analyse(client, alice, pid, "b")
    after = _result(client, alice, pid)["cut_proposals"]
    assert [c["id"] for c in before] == [c["id"] for c in after]
    assert all(c["accepted"] is None for c in after)


# --- probe 4: cancellation is final ---------------------------------------------------


def test_cancel_before_worker_starts_is_final(
    client: TestClient, alice, short_project, monkeypatch
) -> None:
    from app.workers import tasks

    pid, asset = short_project
    monkeypatch.setattr(tasks.run_analysis, "apply_async", lambda *a, **k: None)  # worker is down
    job = _analyse(client, alice, pid, "c")
    assert job["status"] == "queued"
    assert (
        client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=alice).json()["status"]
        == "cancelled"
    )

    out = tasks.run_analysis.run(job["id"], pid, asset["id"])  # the worker picks it up late
    assert out["status"] == "cancelled"
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=alice).json()["status"] == "cancelled"
    assert _result(client, alice, pid)["transcript_segments"] == []  # nothing was produced


def test_cancel_during_run_keeps_previous_results(
    client: TestClient, alice, short_project, monkeypatch, session_factory
) -> None:
    from app.db.models import Job, JobStatus
    from app.workers import tasks

    pid, _ = short_project
    _analyse(client, alice, pid, "ok")
    previous = _result(client, alice, pid)

    real = tasks._analyse_story

    def cancel_midway(segments, settings):
        with session_factory() as other:  # the user cancels from another request
            job = other.query(Job).filter(Job.idempotency_key == "mid").one()
            job.status = JobStatus.cancelled
            other.commit()
        return real(segments, settings)

    monkeypatch.setattr(tasks, "_analyse_story", cancel_midway)
    job = _analyse(client, alice, pid, "mid")
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=alice).json()["status"] == "cancelled"
    now = _result(client, alice, pid)
    assert [s["id"] for s in now["transcript_segments"]] == [
        s["id"] for s in previous["transcript_segments"]
    ]


def test_cancel_finished_job_is_rejected(client: TestClient, alice, short_project) -> None:
    pid, _ = short_project
    job = _analyse(client, alice, pid, "done")
    r = client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=alice)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


# --- probe 5: API_CONTRACT error envelope ---------------------------------------------


def _assert_envelope(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) >= {"error", "request_id"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert isinstance(body["error"]["field_errors"], list)
    assert isinstance(body["error"]["retryable"], bool)
    assert body["request_id"] == r.headers["X-Request-Id"]
    assert "detail" in body  # deprecated alias kept for existing clients
    return body


def test_error_envelope_for_common_errors(client: TestClient, alice, make_project) -> None:
    _assert_envelope(client.get("/api/v1/projects/nope", headers=alice), 404, "NOT_FOUND")
    _assert_envelope(client.get("/api/v1/projects"), 401, "UNAUTHORIZED")
    body = _assert_envelope(
        client.post("/api/v1/projects", json={"title": ""}, headers=alice), 422, "VALIDATION_ERROR"
    )
    assert body["error"]["field_errors"][0]["field"] == "title"
    assert body["error"]["retryable"] is False


def test_request_id_is_echoed_only_when_safe(client: TestClient, alice) -> None:
    uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    ok = client.get("/api/v1/projects/nope", headers={**alice, "X-Request-Id": "abc-123"})
    assert ok.json()["request_id"] == ok.headers["X-Request-Id"] == "abc-123"
    for bad in ("<script>alert(1)</script>", "a b c", "x" * 65):  # unsafe chars, spaces, too long
        r = client.get("/api/v1/projects/nope", headers={**alice, "X-Request-Id": bad})
        assert uuid_re.match(r.headers["X-Request-Id"]), bad
        assert r.json()["request_id"] == r.headers["X-Request-Id"]


def test_request_id_sanitises_non_ascii_header_bytes() -> None:
    """Real clients can send raw UTF-8 header bytes; httpx cannot, so build the request directly."""
    from starlette.requests import Request

    from app.api.errors import request_id_for

    req = Request(
        {"type": "http", "headers": [(b"x-request-id", "x\u00e9<b>".encode())], "state": {}}
    )
    rid = request_id_for(req)
    assert re.match(r"^[0-9a-f-]{36}$", rid)
    assert request_id_for(req) == rid  # stable for the rest of the request


def test_unhandled_error_is_generic(client: TestClient, alice, monkeypatch) -> None:
    import app.api.v1.projects as projects_api
    from app.main import app

    def boom(*a, **k):
        raise RuntimeError("secret path C:\\internal\\db password=hunter2")

    monkeypatch.setattr(projects_api, "list_projects", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/projects", headers=alice)
    body = _assert_envelope(r, 500, "INTERNAL_ERROR")
    assert body["error"]["retryable"] is True
    assert "hunter2" not in r.text and "internal" not in r.text.lower().replace(
        "internal_error", ""
    ).replace("internal server error", "")


# --- probe 6: retry endpoint ------------------------------------------------------------


def test_retry_failed_analysis_reuses_the_job(
    client: TestClient, alice, short_project, monkeypatch
) -> None:
    from app.workers import tasks

    pid, _ = short_project
    real = tasks._analyse_story
    calls = {"n": 0}

    def flaky(segments, settings):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model crashed")
        return real(segments, settings)

    monkeypatch.setattr(tasks, "_analyse_story", flaky)
    job = _analyse(client, alice, pid, "flaky")
    failed = client.get(f"/api/v1/jobs/{job['id']}", headers=alice).json()
    assert failed["status"] == "failed" and failed["retryable"] is True

    r = client.post(f"/api/v1/jobs/{job['id']}/retry", headers=alice)
    assert r.status_code == 202, r.text
    assert r.json()["id"] == job["id"]
    done = client.get(f"/api/v1/jobs/{job['id']}", headers=alice).json()
    assert done["status"] == "completed" and done["retryable"] is False
    assert _result(client, alice, pid)["transcript_segments"]


def test_retry_rules(client: TestClient, alice, bob, short_project, make_project) -> None:
    pid, _ = short_project
    done = _analyse(client, alice, pid, "fine")
    _assert_envelope(
        client.post(f"/api/v1/jobs/{done['id']}/retry", headers=alice), 409, "CONFLICT"
    )
    _assert_envelope(client.post(f"/api/v1/jobs/{done['id']}/retry", headers=bob), 404, "NOT_FOUND")

    # A file that is not a video is a permanent failure.
    other = make_project(alice, "junk")
    junk = b"MZ" + b"not a video" * 200
    g = client.post(
        f"/api/v1/projects/{other}/media/upload-url",
        json={"filename": "j.mp4", "content_type": "video/mp4", "expected_bytes": len(junk)},
        headers=alice,
    ).json()
    client.put(g["upload_url"], content=junk)
    j = client.post(
        f"/api/v1/projects/{other}/media/complete",
        json={"media_asset_id": g["media_asset_id"]},
        headers=alice,
    ).json()
    status = client.get(f"/api/v1/jobs/{j['id']}", headers=alice).json()
    assert status["status"] == "failed" and status["retryable"] is False
    body = _assert_envelope(
        client.post(f"/api/v1/jobs/{j['id']}/retry", headers=alice), 409, "CONFLICT"
    )
    assert "can't be retried" in body["error"]["message"]


def test_retries_are_bounded(client: TestClient, alice, short_project, monkeypatch) -> None:
    from app.workers import tasks

    pid, _ = short_project

    def always_fails(segments, settings):
        raise RuntimeError("down")

    monkeypatch.setattr(tasks, "_analyse_story", always_fails)
    job = _analyse(client, alice, pid, "doomed")
    codes = [
        client.post(f"/api/v1/jobs/{job['id']}/retry", headers=alice).status_code for _ in range(5)
    ]
    assert codes == [202, 202, 202, 409, 409]  # max_retries = 3


# --- probe 7: rate limiting --------------------------------------------------------------


def test_project_creation_is_rate_limited_per_user(client: TestClient, alice, bob) -> None:
    codes = [
        client.post("/api/v1/projects", json={"title": f"p{i}"}, headers=alice).status_code
        for i in range(21)
    ]
    assert codes[:20] == [201] * 20
    r = client.post("/api/v1/projects", json={"title": "one more"}, headers=alice)
    body = _assert_envelope(r, 429, "RATE_LIMITED")
    assert body["error"]["retryable"] is True
    assert int(r.headers["Retry-After"]) > 0
    assert (
        client.post("/api/v1/projects", json={"title": "bob"}, headers=bob).status_code == 201
    )  # per user


def test_rate_limit_can_be_disabled(client: TestClient, alice, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    codes = {
        client.post("/api/v1/projects", json={"title": "x"}, headers=alice).status_code
        for _ in range(25)
    }
    assert codes == {201}


def test_rate_limiter_outage_fails_open(client: TestClient, alice, monkeypatch) -> None:
    from app.api import ratelimit

    class Broken:
        def hit(self, key, window):
            raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "get_store", lambda: Broken())
    assert client.post("/api/v1/projects", json={"title": "x"}, headers=alice).status_code == 201
