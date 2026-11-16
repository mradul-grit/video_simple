from fastapi import FastAPI
from app.api.health import router as health_router
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Story-aware short-form video creation API",
)
app.include_router(health_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": f"{settings.api_v1_prefix}/health/live"}
