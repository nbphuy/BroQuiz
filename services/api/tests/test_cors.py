from fastapi.testclient import TestClient

import app.main as main


NEXTJS_ORIGIN = "http://localhost:3000"


def test_cors_preflight_allows_the_nextjs_development_origin() -> None:
    with TestClient(main.app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": NEXTJS_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == NEXTJS_ORIGIN
    assert "GET" in response.headers["access-control-allow-methods"]


def test_health_response_allows_the_nextjs_development_origin(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database_connection", lambda: None)

    with TestClient(main.app) as client:
        response = client.get("/health", headers={"Origin": NEXTJS_ORIGIN})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["access-control-allow-origin"] == NEXTJS_ORIGIN


def test_cors_rejects_unconfigured_origins() -> None:
    with TestClient(main.app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://malicious.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
