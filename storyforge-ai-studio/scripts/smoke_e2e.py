"""End-to-end smoke test against a running stack (docker compose up).

Usage:  python scripts/smoke_e2e.py [--base http://localhost:8000]
Needs ffmpeg on PATH to generate a test clip. Uses dev-login, so APP_ENV must be
development. Creates one project and deletes it at the end.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def call(base, method, path, body=None, token=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", ctype)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if payload and "json" in r.headers.get("Content-Type", "") else payload)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def wait(base, path, token, label, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, job = call(base, "GET", path, token=token)
        if job["status"] in ("completed", "failed", "cancelled"):
            print(f"  {label}: {job['status']} ({job.get('message')})")
            return job
        time.sleep(1)
    raise SystemExit(f"{label} did not finish in {timeout}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    a = ap.parse_args()
    base = a.base

    s, ready = call(base, "GET", "/api/v1/health/ready")
    print("ready:", s, ready)
    if s != 200:
        return 1

    clip = Path(tempfile.mkdtemp()) / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=12:size=1280x720:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=330:duration=12", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)],
        check=True,
    )  # fmt: skip
    data = clip.read_bytes()

    _, tok = call(base, "POST", "/api/v1/auth/dev-login", {"email": f"smoke-{uuid.uuid4().hex[:8]}@example.com"})
    token = tok["access_token"]
    _, proj = call(base, "POST", "/api/v1/projects", {"title": "Smoke test"}, token)
    pid = proj["id"]
    print("project:", pid)

    _, grant = call(base, "POST", f"/api/v1/projects/{pid}/media/upload-url",
                    {"filename": "clip.mp4", "content_type": "video/mp4", "expected_bytes": len(data)}, token)  # fmt: skip
    s, _ = call(base, "PUT", grant["upload_url"], raw=data, ctype="video/mp4")
    print("upload:", s)
    _, job = call(base, "POST", f"/api/v1/projects/{pid}/media/complete",
                  {"media_asset_id": grant["media_asset_id"]}, token)  # fmt: skip
    if wait(base, f"/api/v1/jobs/{job['id']}", token, "validate")["status"] != "completed":
        return 1

    _, job = call(base, "POST", f"/api/v1/projects/{pid}/analysis", {"idempotency_key": "smoke"}, token)
    if wait(base, f"/api/v1/jobs/{job['id']}", token, "analysis")["status"] != "completed":
        return 1
    _, analysis = call(base, "GET", f"/api/v1/projects/{pid}/analysis", token=token)
    print(f"  segments={len(analysis['transcript_segments'])} cuts={len(analysis['cut_proposals'])}"
          f" captions={len(analysis['editorial_captions'])}")  # fmt: skip

    mid = grant["media_asset_id"]
    manifest = {
        "schema_version": "1.0", "project_id": pid, "version": 1,
        "output": {"width": 1080, "height": 1920, "fps": 30, "container": "mp4",
                   "video_codec": "h264", "audio_codec": "aac"},
        "tracks": [{"id": str(uuid.uuid4()), "type": "video", "items": [
            {"id": str(uuid.uuid4()), "source_media_id": mid, "start": 0.0, "end": 4.0},
            {"id": str(uuid.uuid4()), "source_media_id": mid, "start": 6.0, "end": 10.0},
        ]}],
        "audio_adjustments": {"high_pass_hz": 80, "loudness_target_lufs": -16, "limiter_enabled": True},
    }  # fmt: skip
    s, saved = call(base, "PUT", f"/api/v1/projects/{pid}/edit-manifest",
                    {"expected_version": 0, "manifest_json": manifest}, token)  # fmt: skip
    print("manifest:", s, saved.get("version") if isinstance(saved, dict) else saved)
    _, rj = call(base, "POST", f"/api/v1/projects/{pid}/renders",
                 {"manifest_version": saved["version"], "preset": "preview"}, token)  # fmt: skip
    done = wait(base, f"/api/v1/renders/{rj['id']}", token, "render", timeout=300)
    if done["status"] != "completed":
        return 1
    print(f"  output: {done['output_duration_seconds']:.2f}s, {done['output_size_bytes']} bytes")

    _, dl = call(base, "POST", f"/api/v1/exports/{rj['id']}/download-url", token=token)
    s, mp4 = call(base, "GET", dl["url"])
    out = clip.with_name("export.mp4")
    out.write_bytes(mp4)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(out)],
        capture_output=True, text=True, check=True).stdout)  # fmt: skip
    v = next(x for x in probe["streams"] if x["codec_type"] == "video")
    au = next(x for x in probe["streams"] if x["codec_type"] == "audio")
    print(f"  downloaded: {v['codec_name']} {v['width']}x{v['height']} {v['pix_fmt']},"
          f" {au['codec_name']}, {float(probe['format']['duration']):.2f}s")  # fmt: skip

    s, _ = call(base, "DELETE", f"/api/v1/projects/{pid}", token=token)
    print("delete project:", s)
    s, _ = call(base, "GET", dl["url"])
    print("export link after delete:", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
