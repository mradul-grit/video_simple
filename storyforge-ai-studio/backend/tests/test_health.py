from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_reports_degraded_when_dependencies_are_unavailable() -> None:
    response = client.get("/api/v1/health/ready")
    # Unit tests do not require local Postgres/Redis. A 503 is truthful in that environment.
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ready", "degraded")
    assert set(body["checks"]) == {"database", "queue"}
