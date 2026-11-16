"""Edit manifest endpoints: get, validate, save (optimistic concurrency)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.db.models import MediaStatus
from app.domain.manifest_rules import SchemaNotFoundError, validate_schema, validate_semantics
from app.domain.schemas import EditManifestOut, EditManifestSaveRequest
from app.repositories.analysis_repo import list_transcript_segments
from app.repositories.project_repo import (
    get_latest_manifest,
    get_project_owned_by,
    list_media_assets,
    save_manifest,
)

router = APIRouter(prefix="/projects/{project_id}/edit-manifest", tags=["manifest"])


def _assert_project(db, project_id: str, owner_id: str):
    project = get_project_owned_by(db, project_id, owner_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def _all_errors(db, project_id: str, manifest_json: dict) -> list[str]:
    try:
        errors = validate_schema(manifest_json)
    except SchemaNotFoundError as exc:
        raise HTTPException(500, "Manifest schema is not available on the server") from exc
    if errors:
        return errors  # semantic checks assume a structurally valid manifest
    media = {
        a.id: a.duration_seconds or 0.0
        for a in list_media_assets(db, project_id)
        if a.status == MediaStatus.ready
    }
    segment_ids = {s.id for s in list_transcript_segments(db, project_id)}
    return validate_semantics(
        manifest_json, project_id=project_id, media_durations=media, segment_ids=segment_ids
    )


@router.get("", response_model=EditManifestOut)
def get_manifest(project_id: str, current_user: CurrentUser, db: DbSession) -> EditManifestOut:
    _assert_project(db, project_id, current_user.id)
    manifest = get_latest_manifest(db, project_id)
    if manifest is None:
        raise HTTPException(404, "No edit manifest found for this project")
    return EditManifestOut.model_validate(manifest)


@router.post("/validate")
def validate_manifest(
    project_id: str, body: EditManifestSaveRequest, current_user: CurrentUser, db: DbSession
) -> dict:
    _assert_project(db, project_id, current_user.id)
    errors = _all_errors(db, project_id, body.manifest_json)
    return {"valid": not errors, "errors": errors}


@router.put("", response_model=EditManifestOut)
def save_manifest_endpoint(
    project_id: str, body: EditManifestSaveRequest, current_user: CurrentUser, db: DbSession
) -> EditManifestOut:
    """Save a new manifest version.

    `expected_version` is the version the client last saw (0 when none exists).
    A mismatch returns 409 so edits are never silently overwritten.
    """
    _assert_project(db, project_id, current_user.id)
    errors = _all_errors(db, project_id, body.manifest_json)
    if errors:
        raise HTTPException(422, detail={"message": "Manifest validation failed", "errors": errors})
    try:
        manifest = save_manifest(
            db,
            project_id=project_id,
            manifest_json=dict(body.manifest_json),
            expected_version=body.expected_version,
        )
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent save won the race for this version
        db.rollback()
        raise HTTPException(
            409, detail="Manifest was changed by another save. Reload and retry."
        ) from exc
    db.refresh(manifest)
    return EditManifestOut.model_validate(manifest)
