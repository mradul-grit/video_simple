"""Dev-only auth endpoints.

POST /api/v1/auth/dev-login  — create/return a user and issue a JWT.

This endpoint is ONLY available when APP_ENV=development. It must never
appear in a production deployment. It is clearly labelled "demo" in
all responses.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DbSession, create_dev_token
from app.config import settings
from app.db.models import User
from app.domain.schemas import DevLoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/dev-login",
    response_model=TokenResponse,
    summary="[DEV ONLY] Issue a JWT for the given email",
    description=(
        "**Available only when APP_ENV=development.** "
        "Creates the user if not found. Output is labelled as DEMO."
    ),
)
def dev_login(body: DevLoginRequest, request: Request, db: DbSession) -> TokenResponse:
    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login is only available in development environment.",
        )

    user = db.query(User).filter(User.email == body.email).first()
    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            email=body.email,
            display_name=body.display_name or body.email.split("@")[0],
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_dev_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )
