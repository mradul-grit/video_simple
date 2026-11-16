from fastapi import APIRouter, Response, status
from redis import Redis
from sqlalchemy import create_engine, text

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive", "service": settings.app_name}


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    try:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        client.close()
        checks["queue"] = "ok"
    except Exception:
        checks["queue"] = "unavailable"

    is_ready = all(value == "ok" for value in checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "degraded",
        "service": settings.app_name,
        "checks": checks,
    }
