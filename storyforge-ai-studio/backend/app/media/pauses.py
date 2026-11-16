"""Pause detection from the real audio track with FFmpeg's `silencedetect` filter.

Silence is measured, not guessed: an interval where the level stays under
`noise_db` for at least `min_silence` seconds. A pause is still only a *proposal*:
pauses can be rhetorical, so every proposal starts unreviewed and short pauses
get lower confidence.

SECURITY: argv array, no shell; only numbers we format ourselves enter the filter string.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END = re.compile(r"silence_end:\s*(-?[\d.]+)")

# Leave this much silence on each side so cuts do not clip the first/last syllable.
EDGE_PADDING_SECONDS = 0.15


@dataclass(frozen=True)
class Pause:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class PauseDetectionError(RuntimeError):
    pass


def parse_silencedetect(stderr: str, media_duration: float) -> list[Pause]:
    """Parse ffmpeg silencedetect log lines into closed intervals within [0, duration]."""
    pauses: list[Pause] = []
    start: float | None = None
    for line in stderr.splitlines():
        if (m := _START.search(line)) is not None:
            start = max(0.0, float(m.group(1)))
        elif (m := _END.search(line)) is not None and start is not None:
            end = min(media_duration, float(m.group(1)))
            if end > start:
                pauses.append(Pause(start, end))
            start = None
    if start is not None and media_duration > start:  # silence runs to the end of the file
        pauses.append(Pause(start, media_duration))
    return pauses


def detect_pauses(
    path: Path,
    media_duration: float,
    *,
    noise_db: float = -35.0,
    min_silence: float = 0.6,
    timeout: int = 300,
) -> list[Pause]:
    if not -90 <= noise_db <= 0 or not 0.1 <= min_silence <= 10:
        raise ValueError("pause detection thresholds out of range")
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-protocol_whitelist", "file",
        "-i", str(path), "-vn",
        "-af", f"silencedetect=noise={noise_db:.1f}dB:duration={min_silence:.2f}",
        "-f", "null", "-",
    ]  # fmt: skip
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise PauseDetectionError("FFmpeg is not installed on the worker.") from exc
    except subprocess.TimeoutExpired as exc:
        raise PauseDetectionError("Pause detection timed out.") from exc
    if r.returncode != 0:
        raise PauseDetectionError("Could not read the audio track for pause detection.")
    return parse_silencedetect(r.stderr, media_duration)


def pause_cut_proposals(pauses: list[Pause], media_duration: float) -> list[dict]:
    """Turn measured pauses into reviewable cut proposals (never auto-accepted)."""
    proposals = []
    for p in pauses:
        at_start = p.start <= 0.05
        at_end = p.end >= media_duration - 0.05
        start = p.start if at_start else p.start + EDGE_PADDING_SECONDS
        end = p.end if at_end else p.end - EDGE_PADDING_SECONDS
        if end - start < 0.3:
            continue
        if at_start:
            reason, confidence = f"Silence before you start speaking ({p.duration:.1f} s)", 0.9
        elif at_end:
            reason, confidence = f"Silence after you finish ({p.duration:.1f} s)", 0.9
        else:
            # Long gaps are usually dead air; short ones may be deliberate emphasis.
            confidence = round(min(0.9, 0.45 + 0.25 * p.duration), 2)
            note = "" if p.duration >= 1.2 else ", may be a deliberate pause"
            reason = f"Pause of {p.duration:.1f} s with no speech{note}"
        proposals.append(
            {
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "reason": reason,
                "cut_type": "pause",
                "confidence": confidence,
                "segment_sequences": [],
            }
        )
    return proposals
