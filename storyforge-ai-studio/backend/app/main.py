"""StoryForge AI Studio — FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import errors
from app.api.health import router as health_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.auth import router as auth_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.manifest import router as manifest_router
from app.api.v1.media import router as media_router
from app.api.v1.projects import router as projects_router
from app.api.v1.renders import router as renders_router
from app.api.v1.storage import router as storage_router
from app.api.v1.system import router as system_router
from app.api.v1.visual import router as visual_router
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=("Story-aware short-form video creation API. All routes versioned under /api/v1."),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — tighten in production
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def attach_request_id(request: Request, call_next) -> Response:
    request_id = errors.request_id_for(request)
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


errors.install(app)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
_V1 = settings.api_v1_prefix

app.include_router(health_router, prefix=_V1)
app.include_router(system_router, prefix=_V1)
app.include_router(auth_router, prefix=_V1)
app.include_router(projects_router, prefix=_V1)
app.include_router(media_router, prefix=_V1)
app.include_router(analysis_router, prefix=_V1)
app.include_router(visual_router, prefix=_V1)
app.include_router(manifest_router, prefix=_V1)
app.include_router(renders_router, prefix=_V1)
app.include_router(jobs_router, prefix=_V1)

if settings.storage_backend == "local":
    app.include_router(storage_router, prefix=_V1)


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": f"{_V1}/health/live",
    }
