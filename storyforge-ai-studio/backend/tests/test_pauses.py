"""Pause detection runs real ffmpeg on generated audio with known silent gaps."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.media.pauses import (
    EDGE_PADDING_SECONDS,
    Pause,
    detect_pauses,
    parse_silencedetect,
    pause_cut_proposals,
)


def test_detects_the_real_gap(paused_video: Path) -> None:
    pauses = detect_pauses(paused_video, 4.0)
    assert len(pauses) == 1
    assert pauses[0].start == pytest.approx(1.5, abs=0.08)
    assert pauses[0].end == pytest.approx(2.8, abs=0.08)


def test_continuous_audio_has_no_pauses(sample_video: Path) -> None:
    assert detect_pauses(sample_video, 3.0) == []


def test_thresholds_are_validated(sample_video: Path) -> None:
    with pytest.raises(ValueError):
        detect_pauses(sample_video, 3.0, noise_db=5)
    with pytest.raises(ValueError):
        detect_pauses(sample_video, 3.0, min_silence=0)


def test_parser_handles_open_ended_and_clamped_silence() -> None:
    log = "\n".join([
        "[silencedetect @ 0x1] silence_start: -0.01",
        "[silencedetect @ 0x1] silence_end: 0.9 | silence_duration: 0.91",
        "[silencedetect @ 0x1] silence_start: 5.5",
        "[silencedetect @ 0x1] silence_end: 7 | silence_duration: 1.5",
        "[silencedetect @ 0x1] silence_start: 9.2",
    ])  # fmt: skip
    assert parse_silencedetect(log, 10.0) == [Pause(0.0, 0.9), Pause(5.5, 7.0), Pause(9.2, 10.0)]
    assert parse_silencedetect("no silence here", 10.0) == []


def test_proposals_pad_edges_and_scale_confidence() -> None:
    props = pause_cut_proposals(
        [Pause(0.0, 0.9), Pause(5.0, 5.8), Pause(6.0, 8.0), Pause(9.4, 10.0)], 10.0
    )
    by_start = {p["start_seconds"]: p for p in props}
    lead = by_start[0.0]
    # Flush to the file start, but keep padding before the first word.
    assert lead["end_seconds"] == round(0.9 - EDGE_PADDING_SECONDS, 3)
    assert "before you start" in lead["reason"]
    short = by_start[round(5.0 + EDGE_PADDING_SECONDS, 3)]
    assert short["end_seconds"] == round(5.8 - EDGE_PADDING_SECONDS, 3)  # keeps padding by speech
    assert "deliberate" in short["reason"]
    long = by_start[round(6.0 + EDGE_PADDING_SECONDS, 3)]
    assert long["confidence"] > short["confidence"]
    tail = by_start[round(9.4 + EDGE_PADDING_SECONDS, 3)]  # padding after the last word
    assert tail["end_seconds"] == 10.0 and "after you finish" in tail["reason"]
    assert all(p["cut_type"] == "pause" for p in props)


def test_tiny_gaps_are_not_proposed() -> None:
    assert pause_cut_proposals([Pause(3.0, 3.5)], 10.0) == []  # 0.5 s minus padding < 0.3 s


def _analyse(client, headers, pid):
    r = client.post(
        f"/api/v1/projects/{pid}/analysis", json={"idempotency_key": "k"}, headers=headers
    )
    assert r.status_code == 202
    return client.get(f"/api/v1/projects/{pid}/analysis", headers=headers).json()


def test_analysis_proposes_the_measured_pause(
    client: TestClient, alice, make_project, upload_video, paused_video: Path
) -> None:
    pid = make_project(alice)
    upload_video(alice, pid, paused_video)
    cuts = _analyse(client, alice, pid)["cut_proposals"]
    assert len(cuts) == 1
    c = cuts[0]
    assert c["start_seconds"] == pytest.approx(1.5 + EDGE_PADDING_SECONDS, abs=0.1)
    assert c["end_seconds"] == pytest.approx(2.8 - EDGE_PADDING_SECONDS, abs=0.1)
    assert c["accepted"] is None
    assert "[DEMO]" not in c["reason"]  # measured, not demo data


def test_analysis_without_pauses_or_audio_proposes_no_cuts(
    client: TestClient, alice, make_project, upload_video, sample_video: Path, silent_video: Path
) -> None:
    pid = make_project(alice)
    upload_video(alice, pid, sample_video)
    assert _analyse(client, alice, pid)["cut_proposals"] == []
    pid2 = make_project(alice, "no audio")
    upload_video(alice, pid2, silent_video)
    assert _analyse(client, alice, pid2)["cut_proposals"] == []
