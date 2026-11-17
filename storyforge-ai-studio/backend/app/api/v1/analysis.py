"""Analysis endpoints — transcription, story beats, cuts, editorial captions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import CurrentUser, DbSession
from app.api.ratelimit import per_user
from app.db.models import JobStatus, JobType
from app.domain.schemas import (
    AnalysisEnqueueRequest,
    AnalysisResultResponse,
    CutProposalOut,
    CutProposalReviewRequest,
    EditorialCaptionOut,
    JobStatusResponse,
    StoryBeatOut,
    TranscriptSegmentOut,
)
from app.repositories.analysis_repo import (
    get_cut_proposal,
    list_cut_proposals,
    list_editorial_captions,
    list_story_beats,
    list_transcript_segments,
    review_cut_proposal,
)
from app.repositories.project_repo import (
    create_job,
    get_job_by_idempotency,
    get_primary_media_asset,
    get_project_owned_by,
    update_job,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["analysis"])


def _assert_project(db, project_id, owner_id):
    p = get_project_owned_by(db, project_id, owner_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


# ---------------------------------------------------------------------------
# Enqueue analysis
# ---------------------------------------------------------------------------


@router.post(
    "/analysis",
    response_model=JobStatusResponse,
    status_code=202,
    dependencies=[Depends(per_user("analysis:enqueue"))],
)
def enqueue_analysis(
    project_id: str,
    body: AnalysisEnqueueRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> JobStatusResponse:
    _assert_project(db, project_id, current_user.id)

    # Idempotency: return existing job if key already used
    existing = get_job_by_idempotency(db, project_id, body.idempotency_key)
    if existing is not None:
        return JobStatusResponse.model_validate(existing)

    media_asset_id = body.media_asset_id
    if media_asset_id is None:
        primary = get_primary_media_asset(db, project_id)
        if primary is None:
            raise HTTPException(
                422, "No ready media asset found. Upload a video before requesting analysis."
            )
        media_asset_id = primary.id

    job = create_job(
        db,
        project_id=project_id,
        job_type=JobType.transcribe.value,
        media_asset_id=media_asset_id,
        idempotency_key=body.idempotency_key,
    )
    db.commit()
    db.refresh(job)

    # Dispatch to Celery worker
    # Mark queued and commit BEFORE dispatch so a fast worker's result is never overwritten.
    update_job(db, job, status=JobStatus.queued, celery_task_id=job.id)
    db.commit()
    try:
        from app.workers.tasks import run_analysis

        run_analysis.apply_async(
            args=[job.id, project_id, media_asset_id],
            task_id=job.id,
        )
    except Exception as exc:
        update_job(db, job, status=JobStatus.failed, message="Failed to enqueue worker task")
        db.commit()
        raise HTTPException(503, "Worker unavailable — analysis queued locally") from exc

    db.refresh(job)
    return JobStatusResponse.model_validate(job)


# ---------------------------------------------------------------------------
# Poll analysis result
# ---------------------------------------------------------------------------


@router.get("/analysis", response_model=AnalysisResultResponse)
def get_analysis_result(
    project_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> AnalysisResultResponse:
    _assert_project(db, project_id, current_user.id)

    segments = list_transcript_segments(db, project_id)
    beats = list_story_beats(db, project_id)
    cuts = list_cut_proposals(db, project_id)
    captions = list_editorial_captions(db, project_id)

    # Detect language from first segment
    lang = next((s.language for s in segments if s.language), None)
    lang_conf = next((s.confidence for s in segments if s.confidence), None)

    return AnalysisResultResponse(
        transcript_segments=[TranscriptSegmentOut.model_validate(s) for s in segments],
        story_beats=[StoryBeatOut.model_validate(b) for b in beats],
        cut_proposals=[CutProposalOut.model_validate(c) for c in cuts],
        editorial_captions=[EditorialCaptionOut.model_validate(c) for c in captions],
        language_detected=lang,
        language_confidence=lang_conf,
    )


# ---------------------------------------------------------------------------
# Review cut proposals
# ---------------------------------------------------------------------------


@router.patch("/cuts/{cut_id}", response_model=CutProposalOut)
def review_cut(
    project_id: str,
    cut_id: str,
    body: CutProposalReviewRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> CutProposalOut:
    _assert_project(db, project_id, current_user.id)
    cut = get_cut_proposal(db, cut_id, project_id)
    if cut is None:
        raise HTTPException(404, "Cut proposal not found")
    new_start = cut.start_seconds if body.start_seconds is None else body.start_seconds
    new_end = cut.end_seconds if body.end_seconds is None else body.end_seconds
    if new_start < 0 or new_end <= new_start:
        raise HTTPException(422, "A cut needs 0 <= start < end.")
    review_cut_proposal(
        db,
        cut,
        accepted=body.accepted,
        start_seconds=body.start_seconds,
        end_seconds=body.end_seconds,
    )
    db.commit()
    db.refresh(cut)
    return CutProposalOut.model_validate(cut)
