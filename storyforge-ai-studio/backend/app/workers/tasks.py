"""Celery tasks for StoryForge AI Studio.

Each task is idempotent and reports progress via Job DB row updates.
Workers never shell-interpolate user data into subprocess calls.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from celery import Task

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db_and_job(job_id: str):
    """Helper — returns (db session, job row)."""
    from app.db.base import SessionLocal
    from app.repositories.project_repo import get_job

    db = SessionLocal()
    job = get_job(db, job_id)
    return db, job


def _update_job(db, job, **kwargs):
    from app.repositories.project_repo import update_job

    return update_job(db, job, **kwargs)


# ---------------------------------------------------------------------------
# Analysis task (transcription + story analysis)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_analysis",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=3,
    acks_late=True,
)
def run_analysis(self: Task, job_id: str, project_id: str, media_asset_id: str) -> dict:
    """Transcribe audio and run story analysis. Updates DB with results."""
    from app.config import settings
    from app.db.models import JobStatus
    from app.repositories.project_repo import get_media_asset

    db, job = _get_db_and_job(job_id)
    if job is None:
        logger.error("run_analysis: job %s not found", job_id)
        return {"status": "not_found"}

    try:
        _update_job(db, job, status=JobStatus.running, stage="preparing", progress=5)
        db.commit()

        asset = get_media_asset(db, media_asset_id)
        if asset is None or asset.storage_key is None:
            raise ValueError(f"Media asset {media_asset_id} not found or has no storage key")

        from app.storage.factory import get_storage

        storage = get_storage()
        media_path = storage.get_path(asset.storage_key)

        # --- Transcription ---
        _update_job(db, job, stage="transcribing", progress=20)
        db.commit()

        transcript_segments = _transcribe(media_path, project_id, media_asset_id, settings)

        # --- Save transcript ---
        from app.repositories.analysis_repo import save_transcript_segments

        saved_segments = save_transcript_segments(db, project_id, transcript_segments)
        db.commit()

        # --- Story analysis ---
        _update_job(db, job, stage="analysing", progress=55)
        db.commit()

        analysis = _analyse_story(transcript_segments, settings)

        # Attach project and segment IDs to beats/cuts/captions
        seg_id_map = {s.sequence: s.id for s in saved_segments}

        from app.repositories.analysis_repo import (
            save_cut_proposals,
            save_editorial_captions,
            save_story_beats,
        )

        beats_data = []
        for b in analysis.get("beats", []):
            seg_ids = [seg_id_map[i] for i in b.get("segment_sequences", []) if i in seg_id_map]
            beats_data.append({**b, "transcript_segment_ids": seg_ids})
        save_story_beats(db, project_id, beats_data)

        # Pause cuts come from the measured audio, never from the language model.
        cuts_data = []
        if asset.has_audio and asset.duration_seconds:
            from app.media.pauses import detect_pauses, pause_cut_proposals

            _update_job(db, job, stage="detecting_pauses", progress=75)
            db.commit()
            pauses = detect_pauses(media_path, asset.duration_seconds)
            for c in pause_cut_proposals(pauses, asset.duration_seconds):
                cuts_data.append({**c, "media_asset_id": media_asset_id})
        for c in analysis.get("cuts", []):
            if c.get("cut_type") != "filler":
                continue  # only filler-word cuts may come from the language model
            seg_ids = [seg_id_map[i] for i in c.get("segment_sequences", []) if i in seg_id_map]
            cuts_data.append(
                {**c, "media_asset_id": media_asset_id, "transcript_segment_ids": seg_ids}
            )
        save_cut_proposals(db, project_id, cuts_data)

        captions_data = []
        for cap in analysis.get("captions", []):
            seg_ids = [seg_id_map[i] for i in cap.get("segment_sequences", []) if i in seg_id_map]
            low_conf = not seg_ids or cap.get("confidence", 1.0) < 0.6
            captions_data.append(
                {**cap, "transcript_segment_ids": seg_ids, "low_confidence": low_conf}
            )
        save_editorial_captions(db, project_id, captions_data)

        db.commit()

        _update_job(
            db,
            job,
            status=JobStatus.completed,
            stage="completed",
            progress=100,
            message="Analysis complete",
            completed_at=datetime.now(UTC),
        )
        db.commit()

    except Exception:
        logger.exception("run_analysis failed for job %s", job_id)
        try:
            from app.db.models import JobStatus as JS

            _update_job(
                db,
                job,
                status=JS.failed,
                message="Analysis failed. Please retry.",
                error_code="ANALYSIS_ERROR",
            )
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()

    return {"status": "completed", "job_id": job_id}


# ---------------------------------------------------------------------------
# Visual search task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_visual_search",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=2,
    acks_late=True,
)
def run_visual_search(self: Task, job_id: str, project_id: str, beat_ids: list[str]) -> dict:
    from app.config import settings
    from app.db.models import JobStatus
    from app.repositories.analysis_repo import get_story_beat, save_visual_suggestions

    db, job = _get_db_and_job(job_id)
    if job is None:
        return {"status": "not_found"}

    try:
        _update_job(db, job, status=JobStatus.running, stage="searching", progress=10)
        db.commit()

        suggestions = []
        for beat_id in beat_ids:
            beat = get_story_beat(db, beat_id, project_id)
            if beat is None:
                continue
            results = _search_visuals(beat, settings)
            for r in results:
                r["story_beat_id"] = beat_id
            suggestions.extend(results)

        save_visual_suggestions(db, project_id, suggestions)
        db.commit()

        _update_job(
            db,
            job,
            status=JobStatus.completed,
            stage="completed",
            progress=100,
            message=f"Found {len(suggestions)} visual candidates",
            completed_at=datetime.now(UTC),
        )
        db.commit()

    except Exception:
        logger.exception("run_visual_search failed for job %s", job_id)
        try:
            from app.db.models import JobStatus as JS

            _update_job(db, job, status=JS.failed, message="Visual search failed")
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()

    return {"status": "completed", "job_id": job_id}


# ---------------------------------------------------------------------------
# Render task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="app.workers.tasks.run_render", acks_late=True)
def run_render(
    self: Task, render_job_id: str, project_id: str, manifest_id: str, preset: str
) -> dict:
    """Render a manifest version. Only a verified output is ever marked completed."""
    import shutil

    from app.db.base import SessionLocal
    from app.db.models import EditManifest, JobStatus, MediaAsset, MediaStatus
    from app.repositories.project_repo import get_render_job
    from app.services.renderer import (
        RenderError,
        SourceMedia,
        render_manifest,
        video_items,
    )
    from app.storage.factory import get_storage

    db = SessionLocal()
    rj = None
    try:
        rj = get_render_job(db, render_job_id)
        if rj is None:
            return {"status": "not_found"}
        if rj.status == JobStatus.completed:
            return {"status": "completed", "render_job_id": render_job_id}  # idempotent

        rj.status, rj.stage, rj.progress, rj.message = JobStatus.running, "preparing", 5, None
        db.commit()

        manifest = db.get(EditManifest, manifest_id)
        if manifest is None or manifest.project_id != project_id:
            raise RenderError("The edit version to render was not found.")

        storage = get_storage()
        sources: dict[str, SourceMedia] = {}
        for item in video_items(manifest.manifest_json):
            mid = item["source_media_id"]
            if mid in sources:
                continue
            asset = db.get(MediaAsset, mid)
            if (
                asset is None
                or asset.project_id != project_id
                or asset.status != MediaStatus.ready
                or not asset.storage_key
                or not storage.exists(asset.storage_key)
            ):
                raise RenderError("A source video for this edit is no longer available.")
            sources[mid] = SourceMedia(storage.get_path(asset.storage_key), bool(asset.has_audio))

        def progress(pct: int, stage: str) -> None:
            rj.progress, rj.stage = pct, stage
            db.commit()

        output, probe, tmpdir = render_manifest(
            manifest_json=manifest.manifest_json,
            sources=sources,
            preset=preset,
            progress_callback=progress,
        )
        try:
            key = f"projects/{project_id}/renders/{render_job_id}/output.mp4"
            storage.put_file(key, output)
            size = storage.get_path(key).stat().st_size
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        rj.output_storage_key = key
        rj.output_size_bytes = size
        rj.output_duration_seconds = float(probe.get("format", {}).get("duration", 0) or 0)
        rj.output_probe = probe
        rj.status, rj.stage, rj.progress = JobStatus.completed, "completed", 100
        rj.message = "Export ready"
        rj.completed_at = datetime.now(UTC)
        db.commit()
        return {"status": "completed", "render_job_id": render_job_id}

    except RenderError as exc:
        db.rollback()
        if rj is not None:
            rj.status, rj.stage, rj.message = JobStatus.failed, "failed", str(exc)
            rj.output_storage_key = None
            db.commit()
        return {"status": "failed", "render_job_id": render_job_id}
    except Exception:
        logger.exception("run_render crashed for %s", render_job_id)
        db.rollback()
        if rj is not None:
            rj.status, rj.stage = JobStatus.failed, "failed"
            rj.message = "The render failed unexpectedly. Please retry."
            db.commit()
        return {"status": "failed", "render_job_id": render_job_id}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scaffold health task (kept for smoke-testing workers)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="app.workers.tasks.scaffold_health_task")
def scaffold_health_task(self: Task) -> dict:
    """Harmless worker smoke-test task."""
    return {"status": "ok", "task_id": str(self.request.id)}


# ---------------------------------------------------------------------------
# Provider implementations (mock + real adapters)
# ---------------------------------------------------------------------------


def _transcribe(media_path: Path, project_id: str, media_asset_id: str, settings) -> list[dict]:
    """Return transcript segments. Uses real Faster-Whisper or mock provider."""
    if settings.transcription_provider == "mock":
        return _mock_transcript(media_asset_id)
    elif settings.transcription_provider == "faster_whisper":
        return _whisper_transcribe(media_path, settings)
    else:
        logger.warning(
            "Unknown transcription provider %s, using mock", settings.transcription_provider
        )
        return _mock_transcript(media_asset_id)


def _mock_transcript(media_asset_id: str) -> list[dict]:
    """
    DEMO DATA — clearly labelled as mock output.
    This is returned when transcription_provider=mock.
    Not real transcription output.
    """
    return [
        {
            "sequence": 0,
            "start_seconds": 0.0,
            "end_seconds": 4.5,
            "text": "[DEMO] Hello everyone and welcome to this tutorial.",
            "language": "en",
            "confidence": 0.92,
            "is_speech": True,
            "media_asset_id": media_asset_id,
        },
        {
            "sequence": 1,
            "start_seconds": 4.5,
            "end_seconds": 9.2,
            "text": "[DEMO] Today we are going to explore a fascinating topic.",
            "language": "en",
            "confidence": 0.89,
            "is_speech": True,
            "media_asset_id": media_asset_id,
        },
        {
            "sequence": 2,
            "start_seconds": 9.2,
            "end_seconds": 11.0,
            "text": "",
            "language": "en",
            "confidence": None,
            "is_speech": False,
            "media_asset_id": media_asset_id,
        },
        {
            "sequence": 3,
            "start_seconds": 11.0,
            "end_seconds": 18.5,
            "text": "[DEMO] The key insight is that visual context helps the audience understand complex ideas much more quickly.",  # noqa: E501
            "language": "en",
            "confidence": 0.95,
            "is_speech": True,
            "media_asset_id": media_asset_id,
        },
        {
            "sequence": 4,
            "start_seconds": 18.5,
            "end_seconds": 25.0,
            "text": "[DEMO] So let me show you how to do that step by step.",
            "language": "en",
            "confidence": 0.91,
            "is_speech": True,
            "media_asset_id": media_asset_id,
        },
    ]


def _whisper_transcribe(media_path: Path, settings) -> list[dict]:
    """Transcribe using Faster-Whisper (real provider)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "faster_whisper is not installed. "
            "Install with: pip install faster-whisper  "
            "or switch TRANSCRIPTION_PROVIDER=mock for development."
        ) from exc

    model = WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    segments, info = model.transcribe(str(media_path), beam_size=5, word_timestamps=True)

    rows = []
    for i, seg in enumerate(segments):
        words = None
        if hasattr(seg, "words") and seg.words:
            words = [
                {"word": w.word, "start": w.start, "end": w.end, "prob": w.probability}
                for w in seg.words
            ]
        rows.append(
            {
                "sequence": i,
                "start_seconds": seg.start,
                "end_seconds": seg.end,
                "text": seg.text.strip(),
                "language": info.language,
                "confidence": float(seg.avg_logprob) if hasattr(seg, "avg_logprob") else None,
                "is_speech": True,
                "media_asset_id": "",  # caller sets this
                "words": words,
            }
        )
    return rows


def _analyse_story(transcript_segments: list[dict], settings) -> dict:
    """Return story beats, cut proposals and editorial captions."""
    if settings.llm_provider == "mock":
        return _mock_story_analysis(transcript_segments)
    elif settings.llm_provider == "ollama":
        return _ollama_story_analysis(transcript_segments, settings)
    else:
        return _mock_story_analysis(transcript_segments)


def _mock_story_analysis(segments: list[dict]) -> dict:
    """
    DEMO DATA — mock story analysis.
    Real output requires llm_provider=ollama with a configured model.
    """
    speech_segs = [s for s in segments if s.get("is_speech") and s.get("text", "").strip()]
    if not speech_segs:
        return {"beats": [], "cuts": [], "captions": []}

    beats = []
    # Group into ~2 beats for demo
    mid = max(1, len(speech_segs) // 2)
    for idx, group in enumerate([speech_segs[:mid], speech_segs[mid:]]):
        if not group:
            continue
        seq_nums = [s["sequence"] for s in group]
        beats.append(
            {
                "sequence": idx,
                "start_seconds": group[0]["start_seconds"],
                "end_seconds": group[-1]["end_seconds"],
                "topic": f"[DEMO] Topic {idx + 1}",
                "summary": " ".join(s["text"][:50] for s in group[:2]),
                "segment_sequences": seq_nums,
                "visual_query_terms": ["education", "tutorial", "concept"],
                "visual_query_rationale": "[DEMO] Mock visual query based on topic keywords.",
                "confidence": 0.75,
            }
        )

    # Pause cuts are measured from the audio (app.media.pauses), not invented here.
    cuts: list[dict] = []

    # Editorial captions grounded in speech segments
    captions = []
    for i, seg in enumerate(speech_segs[:3]):
        captions.append(
            {
                "sequence": i,
                "start_seconds": seg["start_seconds"],
                "end_seconds": seg["end_seconds"],
                "text": f"[DEMO CAPTION] {seg['text'][:60]}",
                "segment_sequences": [seg["sequence"]],
                "confidence": 0.70,
            }
        )

    return {"beats": beats, "cuts": cuts, "captions": captions}


def _ollama_story_analysis(segments: list[dict], settings) -> dict:
    """Call Ollama for story analysis with strict JSON output."""
    import json as _json

    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx required for Ollama provider") from exc

    speech_text = "\n".join(
        f"[{s['sequence']}] {s['start_seconds']:.1f}s-{s['end_seconds']:.1f}s: {s['text']}"  # noqa: E501
        for s in segments
        if s.get("is_speech") and s.get("text", "").strip()
    )

    prompt = f"""You are a video editing assistant. Analyse this transcript; return JSON only.

Transcript:
{speech_text}

Return JSON with this exact structure:
{{
  "beats": [
    {{
      "sequence": 0,
      "start_seconds": 0.0,
      "end_seconds": 10.0,
      "topic": "topic phrase",
      "summary": "one sentence summary",
      "segment_sequences": [0, 1],
      "visual_query_terms": ["term1", "term2"],
      "visual_query_rationale": "why these terms",
      "confidence": 0.85
    }}
  ],
  "cuts": [
    {{
      "start_seconds": 5.0,
      "end_seconds": 6.5,
      "reason": "long pause",
      "cut_type": "pause",
      "confidence": 0.9,
      "segment_sequences": []
    }}
  ],
  "captions": [
    {{
      "sequence": 0,
      "start_seconds": 0.0,
      "end_seconds": 4.0,
      "text": "concise key point, max 8 words",
      "segment_sequences": [0],
      "confidence": 0.8
    }}
  ]
}}

Rules:
- editorial captions must cite segment_sequences (non-empty list of integers)
- captions must be concise and grounded in transcript text, do not add facts
- confidence is 0.0-1.0
- return only the JSON object, no commentary"""

    try:
        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        # Extract JSON from response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return _json.loads(raw[start:end])
    except Exception as exc:
        logger.warning("Ollama story analysis failed: %s — falling back to mock", exc)

    return _mock_story_analysis(segments)


def _search_visuals(beat, settings) -> list[dict]:
    """Search for visual assets relevant to a story beat."""
    if settings.visual_search_provider == "openverse":
        return _openverse_search(beat, settings)
    return []


def _openverse_search(beat, settings) -> list[dict]:
    """Search Openverse for open-licensed images."""
    import httpx

    terms = beat.visual_query_terms or []
    if not terms:
        return []

    query = " ".join(terms[:3])
    try:
        resp = httpx.get(
            "https://api.openverse.org/v1/images/",
            params={
                "q": query,
                "license_type": "commercial",
                "mature": "false",
                "page_size": 5,
            },
            timeout=15,
            headers={"User-Agent": "StoryForge-AI-Studio/0.1 (dev)"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Openverse search failed: %s", exc)
        return []

    results = []
    for item in data.get("results", []):
        license_id = item.get("license", "")
        # Skip non-commercial and no-derivatives licenses
        skip_patterns = ["nc", "nd", "noncommercial", "noderivatives"]
        if any(p in license_id.lower() for p in skip_patterns):
            continue

        results.append(
            {
                "provider": "openverse",
                "external_id": item.get("id"),
                "preview_url": item.get("thumbnail"),
                "source_url": item.get("foreign_landing_url") or item.get("url", ""),
                "creator": item.get("creator"),
                "license_spdx": _normalise_license(license_id),
                "attribution_text": item.get("attribution"),
                "relevance_score": None,
                "suggested_start_seconds": beat.start_seconds,
                "suggested_end_seconds": min(beat.start_seconds + 5.0, beat.end_seconds),
            }
        )

    return results


def _normalise_license(raw: str) -> str | None:
    """Convert Openverse license string to SPDX where possible."""
    mapping = {
        "cc0": "CC0-1.0",
        "pdm": "LicenseRef-PublicDomain",
        "by": "CC-BY-4.0",
        "by-sa": "CC-BY-SA-4.0",
        "by-nc": "CC-BY-NC-4.0",
        "by-nd": "CC-BY-ND-4.0",
        "by-nc-sa": "CC-BY-NC-SA-4.0",
        "by-nc-nd": "CC-BY-NC-ND-4.0",
    }
    return mapping.get(raw.lower().strip())


# ---------------------------------------------------------------------------
# Media validation task (ffprobe, size, duration) - never run in an HTTP request
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="app.workers.tasks.run_media_validation", acks_late=True)
def run_media_validation(self: Task, job_id: str, media_asset_id: str) -> dict:
    from app.repositories.project_repo import get_media_asset
    from app.services.ingest import validate_media_asset
    from app.storage.factory import get_storage

    db, job = _get_db_and_job(job_id)
    try:
        asset = get_media_asset(db, media_asset_id)
        if job is None or asset is None:
            return {"status": "not_found"}
        validate_media_asset(db, get_storage(), asset, job)
        return {"status": asset.status.value, "job_id": job_id}
    finally:
        db.close()
