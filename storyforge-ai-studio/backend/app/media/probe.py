"""ffprobe-based media validation and metadata extraction.

SECURITY: ffprobe is invoked with an explicit argv array. Never use shell=True
or string interpolation with user-supplied data. Input paths are validated
to be within the storage root before being passed to the subprocess.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaProbeError(ValueError):
    """Raised when ffprobe cannot parse or the file is invalid."""


@dataclass(frozen=True)
class MediaMetadata:
    duration_seconds: float
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool
    has_video: bool
    orientation: int  # degrees (0, 90, 180, 270)
    raw: dict  # full ffprobe JSON


# Supported file magic byte signatures mapped to allowed content-types
_MAGIC_SIGNATURES: list[tuple[bytes, list[str]]] = [
    (b"\x00\x00\x00\x18ftyp", ["video/mp4", "video/quicktime"]),
    (b"\x00\x00\x00\x1cftyp", ["video/mp4"]),
    (b"\x00\x00\x00\x20ftyp", ["video/mp4"]),
    (b"\x1aE\xdf\xa3", ["video/webm", "video/x-matroska"]),
    (b"RIFF", ["video/avi", "video/x-msvideo"]),
    (b"\x30\x26\xb2\x75", ["video/x-ms-wmv"]),
    (b"\x00\x00\x01\xba", ["video/mpeg"]),
    (b"\x00\x00\x01\xb3", ["video/mpeg"]),
    # MKV/WebM
    (b"\x1a\x45\xdf\xa3", ["video/webm", "video/x-matroska"]),
]


def validate_file_signature(path: Path, declared_content_type: str | None) -> None:
    """Confirm path begins with a recognised video magic sequence.

    Raises MediaProbeError on mismatch to protect against MIME spoofing.
    """
    with path.open("rb") as f:
        header = f.read(32)

    # Quick heuristic: ftyp box at various offsets for MP4/MOV
    if b"ftyp" in header[:16]:
        return  # accept MP4/MOV

    for magic, _ in _MAGIC_SIGNATURES:
        if header[: len(magic)] == magic:
            return

    raise MediaProbeError(
        "File signature does not match a supported video format. "
        "Accepted: MP4, MOV, MKV, WebM, AVI, MPEG."
    )


def probe(path: Path) -> MediaMetadata:
    """Run ffprobe and return structured MediaMetadata.

    Raises MediaProbeError if ffprobe fails or returns unexpected output.
    Path must already be validated as within the storage root.
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),  # explicit str, no shell expansion
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaProbeError("ffprobe not found. Install FFmpeg to process media.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError("ffprobe timed out analysing the file.") from exc

    if result.returncode != 0:
        raise MediaProbeError(f"ffprobe failed (exit {result.returncode})")

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError(f"ffprobe returned invalid JSON: {exc}") from exc

    return _parse_probe(raw)


def _parse_probe(raw: dict) -> MediaMetadata:
    streams = raw.get("streams", [])
    fmt = raw.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not video_stream and not audio_stream:
        raise MediaProbeError("File contains no recognised video or audio streams.")

    # Duration
    try:
        duration = float(fmt.get("duration") or video_stream.get("duration", 0) or 0)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        duration = 0.0

    # Video properties
    width = height = fps = video_codec = None
    orientation = 0
    if video_stream:
        width = video_stream.get("width")
        height = video_stream.get("height")
        video_codec = video_stream.get("codec_name")
        fps = _parse_fps(video_stream.get("r_frame_rate") or video_stream.get("avg_frame_rate"))
        # Rotation from side_data or tags
        orientation = _parse_orientation(video_stream)

    audio_codec = audio_stream.get("codec_name") if audio_stream else None

    return MediaMetadata(
        duration_seconds=duration,
        width=width,
        height=height,
        fps=fps,
        video_codec=video_codec,
        audio_codec=audio_codec,
        has_audio=audio_stream is not None,
        has_video=video_stream is not None,
        orientation=orientation,
        raw=raw,
    )


def _parse_fps(fps_str: str | None) -> float | None:
    if not fps_str or fps_str in ("0/0", "0"):
        return None
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/")
            den_int = int(den)
            if den_int == 0:
                return None
            return round(int(num) / den_int, 3)
        return float(fps_str)
    except (ValueError, ZeroDivisionError):
        return None


def _parse_orientation(stream: dict) -> int:
    """Extract rotation from stream side_data or tags."""
    for side in stream.get("side_data_list", []):
        if side.get("side_data_type") == "Display Matrix":
            rot = side.get("rotation", 0)
            return int(rot) % 360
    tags = stream.get("tags", {})
    rot_str = tags.get("rotate") or tags.get("rotation") or "0"
    try:
        return int(rot_str) % 360
    except ValueError:
        return 0
