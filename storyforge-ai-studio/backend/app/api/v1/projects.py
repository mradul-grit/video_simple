"""Project CRUD endpoints — /api/v1/projects."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.api.ratelimit import per_user
from app.domain.schemas import (
    ProjectCreate,
    ProjectListResponse,
    ProjectOut,
    ProjectUpdate,
)
from app.repositories.project_repo import (
    create_project,
    get_project_owned_by,
    list_projects,
    mark_project_deleting,
    update_project,
)
from app.storage.factory import get_storage

router = APIRouter(prefix="/projects", tags=["projects"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(per_user("projects:create"))],
)
def create_project_endpoint(
    body: ProjectCreate,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectOut:
    project = create_project(
        db,
        owner_id=current_user.id,
        title=body.title,
        language_preference=body.language_preference,
        output_preset=body.output_preset,
    )
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("", response_model=ProjectListResponse)
def list_projects_endpoint(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    limit: int = 20,
    cursor: str | None = None,
) -> ProjectListResponse:
    limit = max(1, min(limit, 100))
    rows, total, next_cursor = list_projects(db, current_user.id, limit=limit, cursor=cursor)
    items = [ProjectOut.model_validate(r) for r in rows]
    return ProjectListResponse(items=items, total=total, cursor=next_cursor)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project_endpoint(
    project_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectOut:
    project = get_project_owned_by(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project_endpoint(
    project_id: str,
    body: ProjectUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectOut:
    project = get_project_owned_by(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    update_project(
        db,
        project,
        title=body.title,
        language_preference=body.language_preference,
        output_preset=body.output_preset,
    )
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(
    project_id: str,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete the project, its rows and every stored object (originals, renders).

    Runs synchronously for the local adapter. Backups and cloud lifecycle copies
    are outside this call; see SECURITY_PRIVACY.md for the documented limits.
    """
    project = get_project_owned_by(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    mark_project_deleting(db, project)
    db.commit()
    get_storage().delete_prefix(f"projects/{project_id}")
    db.delete(project)  # ORM cascade removes media, jobs, transcript, manifests, renders
    db.commit()
