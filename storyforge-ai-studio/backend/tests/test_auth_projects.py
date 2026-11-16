from __future__ import annotations

from fastapi.testclient import TestClient


def test_protected_route_requires_token(client: TestClient) -> None:
    assert client.get("/api/v1/projects").status_code == 401


def test_garbage_token_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/projects", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_dev_login_disabled_outside_development(client: TestClient, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    r = client.post("/api/v1/auth/dev-login", json={"email": "x@example.com"})
    assert r.status_code == 403


def test_request_id_header_is_returned(client: TestClient) -> None:
    r = client.get("/api/v1/health/live", headers={"X-Request-Id": "abc-123"})
    assert r.headers["X-Request-Id"] == "abc-123"
    assert "X-Request-Id" in client.get("/api/v1/health/live").headers


def test_project_crud(client: TestClient, alice, make_project) -> None:
    pid = make_project(alice, "My first video")
    got = client.get(f"/api/v1/projects/{pid}", headers=alice).json()
    assert got["title"] == "My first video"
    assert got["language_preference"] == "auto"

    patched = client.patch(
        f"/api/v1/projects/{pid}",
        json={"title": "Renamed", "language_preference": "hi"},
        headers=alice,
    ).json()
    assert patched["title"] == "Renamed"
    assert patched["language_preference"] == "hi"

    listing = client.get("/api/v1/projects", headers=alice).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == pid


def test_project_validation(client: TestClient, alice) -> None:
    assert client.post("/api/v1/projects", json={"title": ""}, headers=alice).status_code == 422
    assert client.post("/api/v1/projects", json={}, headers=alice).status_code == 422


def test_projects_are_private_between_users(client: TestClient, alice, bob, make_project) -> None:
    pid = make_project(alice)
    assert client.get(f"/api/v1/projects/{pid}", headers=bob).status_code == 404
    assert (
        client.patch(f"/api/v1/projects/{pid}", json={"title": "x"}, headers=bob).status_code == 404
    )
    assert client.delete(f"/api/v1/projects/{pid}", headers=bob).status_code == 404
    assert client.get("/api/v1/projects", headers=bob).json()["total"] == 0
    # still intact for the owner
    assert client.get(f"/api/v1/projects/{pid}", headers=alice).status_code == 200


def test_project_pagination(client: TestClient, alice, make_project) -> None:
    ids = [make_project(alice, f"p{i}") for i in range(5)]
    seen: list[str] = []
    cursor = None
    for _ in range(5):
        url = "/api/v1/projects?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(url, headers=alice).json()
        assert page["total"] == 5
        seen += [p["id"] for p in page["items"]]
        cursor = page["cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(ids)
    assert len(seen) == len(set(seen))


def test_nested_routes_do_not_leak_other_users_projects(
    client: TestClient, alice, bob, make_project
) -> None:
    pid = make_project(alice)
    for path in ("media", "analysis", "visual-suggestions", "edit-manifest", "exports"):
        assert client.get(f"/api/v1/projects/{pid}/{path}", headers=bob).status_code == 404, path
