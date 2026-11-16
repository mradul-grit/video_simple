"""Deterministic FFmpeg renderer driven by a validated edit manifest.

Implemented: source cuts (concatenated in manifest order), 9:16 scale/pad,
colour adjustments, audio filters (high-pass, denoise, loudness, limiter),
guaranteed audio track (silence is synthesised for sources without audio).
NOT implemented yet: visual overlays/cutaways, caption burn-in, motion.

SECURITY
- argv arrays only, never a shell. Every number placed in a filtergraph is formatted
  from a validated float/int, never from raw strings.
- Input paths come from server-side storage keys, never from user input.
- Output is probed with ffprobe and must contain H.264 video, AAC audio, 1080x1920
  before it can be reported as completed.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
AUDIO_RATE = 48000

# preset -> (x264 crf, x264 preset, max video bitrate, audio bitrate)
PRESETS: Mapping[str, tuple[int, str, str, str]] = {
    "preview": (28, "veryfast", "2500k", "128k"),
    "balanced": (23, "medium", "6000k", "192k"),
    "high": (18, "slow", "12000k", "256k"),
}


class RenderError(RuntimeError):
    """Raised with a message that is safe to show to the user."""


@dataclass(frozen=True)
class SourceMedia:
    path: Path
    has_audio: bool


def _num(value: float) -> str:
    """Format a number for a filtergraph (no locale, no exponent surprises)."""
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def video_items(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    for track in manifest.get("tracks", []):
        if track.get("type") == "video":
            return list(track.get("items", []))
    return []


def expected_duration(manifest: Mapping[str, Any]) -> float:
    return sum(float(i["end"]) - float(i["start"]) for i in video_items(manifest))


def color_filter(adj: Mapping[str, Any] | None) -> str:
    if not adj:
        return ""
    parts = []
    exposure = float(adj.get("exposure", 0.0))
    contrast = float(adj.get("contrast", 1.0))
    saturation = float(adj.get("saturation", 1.0))
    if exposure or contrast != 1.0 or saturation != 1.0:
        brightness = max(-1.0, min(1.0, exposure * 0.1))
        parts.append(
            f"eq=brightness={_num(brightness)}:contrast={_num(contrast)}"
            f":saturation={_num(saturation)}"
        )
    temperature = float(adj.get("temperature", 0.0))
    if temperature:
        t = temperature / 100.0
        parts.append(f"colorchannelmixer=rr={_num(1 + t * 0.1)}:bb={_num(1 - t * 0.1)}")
    return ",".join(parts)


def audio_filter(adj: Mapping[str, Any] | None) -> str:
    if not adj:
        return ""
    parts = []
    hp = int(adj.get("high_pass_hz", 0) or 0)
    if hp > 0:
        parts.append(f"highpass=f={hp}")
    nr = adj.get("noise_reduction", "off")
    if nr == "light":
        parts.append("afftdn=nf=-20")
    elif nr == "standard":
        parts.append("afftdn=nf=-30")
    if "loudness_target_lufs" in adj:
        parts.append(f"loudnorm=I={_num(adj['loudness_target_lufs'])}:TP=-1.5:LRA=11")
    if adj.get("limiter_enabled"):
        parts.append("alimiter=limit=0.95")
    return ",".join(parts)


def build_command(
    manifest: Mapping[str, Any],
    sources: Mapping[str, SourceMedia],
    output_path: Path,
    preset: str,
) -> list[str]:
    """Return the ffmpeg argv for *manifest*. Pure function, unit-testable."""
    items = video_items(manifest)
    if not items:
        raise RenderError("The edit has no video to render.")
    if preset not in PRESETS:
        raise RenderError(f"Unknown quality preset {preset!r}.")
    crf, x264_preset, maxrate, abitrate = PRESETS[preset]
    fps = float(manifest.get("output", {}).get("fps", 30))

    media_ids: list[str] = []
    for item in items:
        mid = item["source_media_id"]
        if mid not in sources:
            raise RenderError("A source video for this edit is no longer available.")
        if mid not in media_ids:
            media_ids.append(mid)
    index = {mid: i for i, mid in enumerate(media_ids)}

    cmd: list[str] = ["ffmpeg", "-y", "-nostdin", "-v", "error", "-protocol_whitelist", "file"]
    for mid in media_ids:
        cmd += ["-i", str(sources[mid].path)]

    cf = color_filter(manifest.get("color_adjustments"))
    graph: list[str] = []
    labels: list[str] = []
    for n, item in enumerate(items):
        i = index[item["source_media_id"]]
        start, end = float(item["start"]), float(item["end"])
        dur = end - start
        vchain = (
            f"[{i}:v]trim=start={_num(start)}:end={_num(end)},setpts=PTS-STARTPTS,"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={_num(fps)},format=yuv420p"
        )
        if cf:
            vchain += f",{cf}"
        graph.append(f"{vchain}[v{n}]")

        if sources[item["source_media_id"]].has_audio:
            achain = (
                f"[{i}:a]atrim=start={_num(start)}:end={_num(end)},asetpts=PTS-STARTPTS,"
                f"aresample={AUDIO_RATE},aformat=channel_layouts=stereo"
            )
        else:  # keep A/V in step: synthesise silence of the exact length
            achain = (
                f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={_num(dur)},asetpts=PTS-STARTPTS"
            )
        graph.append(f"{achain}[a{n}]")
        labels.append(f"[v{n}][a{n}]")

    graph.append(f"{''.join(labels)}concat=n={len(items)}:v=1:a=1[vcat][acat]")
    af = audio_filter(manifest.get("audio_adjustments"))
    graph.append(f"[acat]{af if af else 'anull'}[aout]")
    graph.append("[vcat]null[vout]")

    cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]"]
    cmd += [
        "-c:v", "libx264", "-preset", x264_preset, "-crf", str(crf),
        "-maxrate", maxrate, "-bufsize", f"{int(maxrate[:-1]) * 2}k",
        "-c:a", "aac", "-b:a", abitrate, "-ar", str(AUDIO_RATE),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(output_path),
    ]  # fmt: skip
    return cmd


def probe_output(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )  # fmt: skip
    if result.returncode != 0:
        raise RenderError("The rendered file could not be read back.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RenderError("The rendered file could not be read back.") from exc


def verify_output(probe: Mapping[str, Any], expected_seconds: float) -> None:
    """Gate before a render may be marked completed."""
    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        raise RenderError("The rendered file is missing a video or audio track.")
    if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
        raise RenderError("The rendered file is not H.264/AAC.")
    if (video.get("width"), video.get("height")) != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
        raise RenderError("The rendered file has the wrong dimensions.")
    if video.get("pix_fmt") != "yuv420p":
        raise RenderError("The rendered file has an unsupported pixel format.")
    duration = float(probe.get("format", {}).get("duration", 0) or 0)
    # One frame of rounding per cut plus audio frame padding.
    if abs(duration - expected_seconds) > max(0.35, expected_seconds * 0.03):
        raise RenderError("The rendered duration does not match the edit.")


def render_manifest(
    *,
    manifest_json: Mapping[str, Any],
    sources: Mapping[str, SourceMedia],
    preset: str,
    timeout_seconds: int = 900,
    progress_callback: Callable[[int, str], None] | None = None,
) -> tuple[Path, dict[str, Any], Path]:
    """Render to a temp dir. Returns (output_path, probe, tmpdir); caller must remove tmpdir.

    The caller moves the verified file into storage; nothing is stored on failure.
    """
    notify = progress_callback or (lambda _p, _s: None)
    tmpdir = Path(tempfile.mkdtemp(prefix="sf_render_"))
    try:
        output = tmpdir / "output.mp4"
        notify(15, "building")
        cmd = build_command(manifest_json, sources, output, preset)
        notify(25, "rendering")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError("The render took too long and was stopped.") from exc
        except FileNotFoundError as exc:
            raise RenderError("FFmpeg is not installed on the render worker.") from exc
        if result.returncode != 0:
            logger.error("ffmpeg failed (exit %s): %s", result.returncode, result.stderr[-1500:])
            raise RenderError("The video could not be rendered. See server logs.")
        notify(85, "verifying")
        probe = probe_output(output)
        verify_output(probe, expected_duration(manifest_json))
        return output, probe, tmpdir
    except BaseException:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
