"""Render tests run real ffmpeg and inspect the output with ffprobe."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.renderer import (
    RenderError,
    SourceMedia,
    audio_filter,
    build_command,
    color_filter,
    verify_output,
)


def _manifest(pid: str, items: list[dict], **extra) -> dict:
    m = {
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
        "tracks": [{"id": str(uuid.uuid4()), "type": "video", "items": items}],
    }
    m.update(extra)
    return m


def _item(media_id: str, start: float, end: float) -> dict:
    return {"id": str(uuid.uuid4()), "source_media_id": media_id, "start": start, "end": end}


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return json.loads(out.stdout)


def _render(client, headers, pid, manifest, preset="preview", expected=0):
    saved = client.put(
        f"/api/v1/projects/{pid}/edit-manifest",
        json={"expected_version": expected, "manifest_json": manifest},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    r = client.post(
        f"/api/v1/projects/{pid}/renders",
        json={"manifest_version": saved.json()["version"], "preset": preset},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    return client.get(f"/api/v1/renders/{r.json()['id']}", headers=headers).json()


def _download(client, headers, render_id, tmp_path: Path) -> Path:
    r = client.post(f"/api/v1/exports/{render_id}/download-url", headers=headers)
    assert r.status_code == 200, r.text
    got = client.get(r.json()["url"])
    assert got.status_code == 200
    out = tmp_path / "export.mp4"
    out.write_bytes(got.content)
    return out


def _streams(probe: dict) -> tuple[dict, dict]:
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    return v, a


def test_render_single_cut_meets_export_baseline(
    client: TestClient, alice, make_project, upload_video, sample_video: Path, tmp_path: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    job = _render(client, alice, pid, _manifest(pid, [_item(asset["id"], 0.5, 2.5)]))
    assert job["status"] == "completed", job
    assert job["progress"] == 100

    out = _download(client, alice, job["id"], tmp_path)
    probe = _probe(out)
    v, a = _streams(probe)
    assert (v["width"], v["height"]) == (1080, 1920)
    assert v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p"
    assert a["codec_name"] == "aac"
    assert float(probe["format"]["duration"]) == pytest.approx(2.0, abs=0.15)
    # A/V in sync: stream durations agree
    assert abs(float(v["duration"]) - float(a["duration"])) < 0.15
    # fast-start: the moov atom comes before the media data
    head = out.read_bytes()
    assert head.find(b"moov") < head.find(b"mdat")


def test_render_joins_cuts_of_the_same_source(
    client: TestClient, alice, make_project, upload_video, sample_video: Path, tmp_path: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    items = [_item(asset["id"], 0.0, 1.0), _item(asset["id"], 2.0, 3.0)]
    job = _render(client, alice, pid, _manifest(pid, items))
    assert job["status"] == "completed", job
    probe = _probe(_download(client, alice, job["id"], tmp_path))
    assert float(probe["format"]["duration"]) == pytest.approx(2.0, abs=0.2)


def test_render_source_without_audio_still_has_audio_track(
    client: TestClient, alice, make_project, upload_video, silent_video: Path, tmp_path: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, silent_video)
    assert asset["has_audio"] is False
    job = _render(client, alice, pid, _manifest(pid, [_item(asset["id"], 0.0, 1.5)]))
    assert job["status"] == "completed", job
    _, a = _streams(_probe(_download(client, alice, job["id"], tmp_path)))
    assert a["codec_name"] == "aac"


def test_render_applies_audio_and_color_adjustments(
    client: TestClient, alice, make_project, upload_video, sample_video: Path, tmp_path: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    m = _manifest(
        pid,
        [_item(asset["id"], 0.0, 2.0)],
        audio_adjustments={
            "noise_reduction": "light",
            "high_pass_hz": 80,
            "loudness_target_lufs": -16,
            "limiter_enabled": True,
        },
        color_adjustments={"exposure": 0.5, "contrast": 1.1, "saturation": 1.2, "temperature": 10},
    )
    job = _render(client, alice, pid, m, preset="balanced")
    assert job["status"] == "completed", job
    probe = _probe(_download(client, alice, job["id"], tmp_path))
    assert float(probe["format"]["duration"]) == pytest.approx(2.0, abs=0.3)


def test_failed_render_is_never_listed_as_completed(
    client: TestClient, alice, make_project, upload_video, sample_video: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    manifest = _manifest(pid, [_item(asset["id"], 0.0, 1.0)])
    saved = client.put(
        f"/api/v1/projects/{pid}/edit-manifest",
        json={"expected_version": 0, "manifest_json": manifest},
        headers=alice,
    )
    # The source goes away between save and render.
    client.delete(f"/api/v1/projects/{pid}/media/{asset['id']}", headers=alice)
    r = client.post(
        f"/api/v1/projects/{pid}/renders",
        json={"manifest_version": saved.json()["version"], "preset": "preview"},
        headers=alice,
    )
    job = client.get(f"/api/v1/renders/{r.json()['id']}", headers=alice).json()
    assert job["status"] == "failed"
    assert "no longer available" in job["message"]
    dl = client.post(f"/api/v1/exports/{job['id']}/download-url", headers=alice)
    assert dl.status_code == 409


def test_export_is_private(
    client: TestClient, alice, bob, make_project, upload_video, sample_video: Path
) -> None:
    pid = make_project(alice)
    asset = upload_video(alice, pid, sample_video)
    job = _render(client, alice, pid, _manifest(pid, [_item(asset["id"], 0.0, 1.0)]))
    assert client.get(f"/api/v1/renders/{job['id']}", headers=bob).status_code == 404
    assert client.post(f"/api/v1/exports/{job['id']}/download-url", headers=bob).status_code == 404
    assert client.get(f"/api/v1/projects/{pid}/exports", headers=bob).status_code == 404
    listing = client.get(f"/api/v1/projects/{pid}/exports", headers=alice).json()
    assert [j["id"] for j in listing] == [job["id"]]


def test_render_unknown_manifest_version(client: TestClient, alice, make_project) -> None:
    pid = make_project(alice)
    r = client.post(
        f"/api/v1/projects/{pid}/renders",
        json={"manifest_version": 7, "preset": "preview"},
        headers=alice,
    )
    assert r.status_code == 404


def test_render_rejects_unknown_preset(client: TestClient, alice, make_project) -> None:
    pid = make_project(alice)
    r = client.post(
        f"/api/v1/projects/{pid}/renders",
        json={"manifest_version": 1, "preset": "ultra; rm -rf /"},
        headers=alice,
    )
    assert r.status_code == 422


# ---------------------- pure unit tests of the command builder -----------------------


def _cmd(items, sources, **extra):
    return build_command(_manifest("p", items, **extra), sources, Path("out.mp4"), "preview")


def test_command_is_an_argv_list_with_no_shell_metacharacters_from_user_data() -> None:
    evil = "x; rm -rf / #"
    sources = {"m1": SourceMedia(Path(evil + ".mp4"), True)}
    cmd = _cmd([_item("m1", 0, 1)], sources)
    assert isinstance(cmd, list) and all(isinstance(c, str) for c in cmd)
    assert cmd.count(str(Path(evil + ".mp4"))) == 1  # one argv element, never split or joined
    assert "-protocol_whitelist" in cmd and cmd[cmd.index("-protocol_whitelist") + 1] == "file"
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert evil not in graph


def test_command_reuses_a_source_for_many_cuts_with_one_input() -> None:
    sources = {"m1": SourceMedia(Path("a.mp4"), True)}
    cmd = _cmd([_item("m1", 0, 1), _item("m1", 2, 3), _item("m1", 4, 5)], sources)
    assert cmd.count("-i") == 1
    assert "concat=n=3:v=1:a=1" in cmd[cmd.index("-filter_complex") + 1]


def test_command_synthesises_silence_for_silent_sources() -> None:
    cmd = _cmd([_item("m1", 0, 1.5)], {"m1": SourceMedia(Path("a.mp4"), False)})
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "anullsrc" in graph and "[0:a]" not in graph


def test_command_rejects_missing_source_empty_edit_and_bad_preset() -> None:
    with pytest.raises(RenderError):
        _cmd([_item("missing", 0, 1)], {})
    with pytest.raises(RenderError):
        _cmd([], {})
    with pytest.raises(RenderError):
        build_command(
            _manifest("p", [_item("m1", 0, 1)]),
            {"m1": SourceMedia(Path("a.mp4"), True)},
            Path("o.mp4"),
            "nope",
        )


def test_filter_builders() -> None:
    assert color_filter(None) == "" and color_filter({}) == ""
    assert color_filter({"contrast": 1.0, "saturation": 1.0}) == ""
    assert "eq=brightness=0.05" in color_filter({"exposure": 0.5})
    assert audio_filter({}) == ""
    f = audio_filter(
        {
            "high_pass_hz": 80,
            "noise_reduction": "standard",
            "limiter_enabled": True,
            "loudness_target_lufs": -16,
        }
    )
    assert f.index("highpass") < f.index("afftdn") < f.index("loudnorm") < f.index("alimiter")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["streams"].pop(1),  # no audio
        lambda p: p["streams"].pop(0),  # no video
        lambda p: p["streams"][0].update(width=720),
        lambda p: p["streams"][0].update(codec_name="hevc"),
        lambda p: p["streams"][0].update(pix_fmt="yuv444p"),
        lambda p: p["format"].update(duration="9.0"),
    ],
)
def test_verify_output_rejects_bad_exports(mutate) -> None:
    good = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "pix_fmt": "yuv420p",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "2.0"},
    }
    verify_output(good, 2.0)  # baseline passes
    bad = json.loads(json.dumps(good))
    mutate(bad)
    with pytest.raises(RenderError):
        verify_output(bad, 2.0)
