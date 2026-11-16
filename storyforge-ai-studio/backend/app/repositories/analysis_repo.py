"""Analysis repository — transcript, beats, cuts, captions, visual suggestions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CutProposal,
    EditorialCaption,
    StoryBeat,
    TranscriptSegment,
    VisualSuggestion,
)

# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


def save_transcript_segments(
    db: Session, project_id: str, segments: list[dict]
) -> list[TranscriptSegment]:
    # Delete existing segments for this project before saving new ones
    existing = db.query(TranscriptSegment).filter(TranscriptSegment.project_id == project_id).all()
    for s in existing:
        db.delete(s)
    db.flush()

    rows = []
    for seg in segments:
        row = TranscriptSegment(
            project_id=project_id,
            media_asset_id=seg["media_asset_id"],
            sequence=seg["sequence"],
            start_seconds=seg["start_seconds"],
            end_seconds=seg["end_seconds"],
            text=seg["text"],
            language=seg.get("language"),
            confidence=seg.get("confidence"),
            is_speech=seg.get("is_speech", True),
            words=seg.get("words"),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def list_transcript_segments(db: Session, project_id: str) -> list[TranscriptSegment]:
    stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.project_id == project_id)
        .order_by(TranscriptSegment.sequence)
    )
    return list(db.scalars(stmt))


# ---------------------------------------------------------------------------
# Story beats
# ---------------------------------------------------------------------------


def save_story_beats(db: Session, project_id: str, beats: list[dict]) -> list[StoryBeat]:
    existing = db.query(StoryBeat).filter(StoryBeat.project_id == project_id).all()
    for b in existing:
        db.delete(b)
    db.flush()

    rows = []
    for beat in beats:
        row = StoryBeat(
            project_id=project_id,
            sequence=beat["sequence"],
            start_seconds=beat["start_seconds"],
            end_seconds=beat["end_seconds"],
            topic=beat.get("topic"),
            summary=beat.get("summary"),
            transcript_segment_ids=beat.get("transcript_segment_ids", []),
            visual_query_terms=beat.get("visual_query_terms", []),
            visual_query_rationale=beat.get("visual_query_rationale"),
            confidence=beat.get("confidence"),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def list_story_beats(db: Session, project_id: str) -> list[StoryBeat]:
    stmt = select(StoryBeat).where(StoryBeat.project_id == project_id).order_by(StoryBeat.sequence)
    return list(db.scalars(stmt))


def get_story_beat(db: Session, beat_id: str, project_id: str) -> StoryBeat | None:
    stmt = select(StoryBeat).where(
        StoryBeat.id == beat_id,
        StoryBeat.project_id == project_id,
    )
    return db.scalar(stmt)


# ---------------------------------------------------------------------------
# Cut proposals
# ---------------------------------------------------------------------------


def save_cut_proposals(db: Session, project_id: str, proposals: list[dict]) -> list[CutProposal]:
    existing = db.query(CutProposal).filter(CutProposal.project_id == project_id).all()
    for p in existing:
        db.delete(p)
    db.flush()

    rows = []
    for prop in proposals:
        row = CutProposal(
            project_id=project_id,
            media_asset_id=prop["media_asset_id"],
            start_seconds=prop["start_seconds"],
            end_seconds=prop["end_seconds"],
            reason=prop["reason"],
            cut_type=prop["cut_type"],
            confidence=prop["confidence"],
            transcript_segment_ids=prop.get("transcript_segment_ids", []),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def list_cut_proposals(db: Session, project_id: str) -> list[CutProposal]:
    stmt = (
        select(CutProposal)
        .where(CutProposal.project_id == project_id)
        .order_by(CutProposal.start_seconds)
    )
    return list(db.scalars(stmt))


def get_cut_proposal(db: Session, cut_id: str, project_id: str) -> CutProposal | None:
    stmt = select(CutProposal).where(
        CutProposal.id == cut_id,
        CutProposal.project_id == project_id,
    )
    return db.scalar(stmt)


def review_cut_proposal(
    db: Session,
    cut: CutProposal,
    *,
    accepted: bool,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> CutProposal:
    cut.accepted = accepted
    if start_seconds is not None:
        cut.start_seconds = start_seconds
    if end_seconds is not None:
        cut.end_seconds = end_seconds
    db.flush()
    return cut


# ---------------------------------------------------------------------------
# Editorial captions
# ---------------------------------------------------------------------------


def save_editorial_captions(
    db: Session, project_id: str, captions: list[dict]
) -> list[EditorialCaption]:
    existing = db.query(EditorialCaption).filter(EditorialCaption.project_id == project_id).all()
    for c in existing:
        db.delete(c)
    db.flush()

    rows = []
    for cap in captions:
        row = EditorialCaption(
            project_id=project_id,
            sequence=cap["sequence"],
            start_seconds=cap["start_seconds"],
            end_seconds=cap["end_seconds"],
            text=cap["text"],
            transcript_segment_ids=cap.get("transcript_segment_ids", []),
            confidence=cap.get("confidence"),
            low_confidence=cap.get("low_confidence", False),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def list_editorial_captions(db: Session, project_id: str) -> list[EditorialCaption]:
    stmt = (
        select(EditorialCaption)
        .where(EditorialCaption.project_id == project_id)
        .order_by(EditorialCaption.sequence)
    )
    return list(db.scalars(stmt))


# ---------------------------------------------------------------------------
# Visual suggestions
# ---------------------------------------------------------------------------


def save_visual_suggestions(
    db: Session, project_id: str, suggestions: list[dict]
) -> list[VisualSuggestion]:
    rows = []
    for sug in suggestions:
        row = VisualSuggestion(
            project_id=project_id,
            story_beat_id=sug.get("story_beat_id"),
            provider=sug["provider"],
            external_id=sug.get("external_id"),
            preview_url=sug.get("preview_url"),
            source_url=sug["source_url"],
            creator=sug.get("creator"),
            license_spdx=sug.get("license_spdx"),
            attribution_text=sug.get("attribution_text"),
            relevance_score=sug.get("relevance_score"),
            suggested_start_seconds=sug.get("suggested_start_seconds"),
            suggested_end_seconds=sug.get("suggested_end_seconds"),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def list_visual_suggestions(db: Session, project_id: str) -> list[VisualSuggestion]:
    stmt = (
        select(VisualSuggestion)
        .where(VisualSuggestion.project_id == project_id)
        .order_by(VisualSuggestion.relevance_score.desc().nullslast())
    )
    return list(db.scalars(stmt))


def get_visual_suggestion(
    db: Session, suggestion_id: str, project_id: str
) -> VisualSuggestion | None:
    stmt = select(VisualSuggestion).where(
        VisualSuggestion.id == suggestion_id,
        VisualSuggestion.project_id == project_id,
    )
    return db.scalar(stmt)
