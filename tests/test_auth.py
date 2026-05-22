import os

from app import main
from app.config import get_settings

os.environ.setdefault("API_KEY", "test-secret-key")


def test_protected_route_requires_api_key_when_configured(monkeypatch, client):
    monkeypatch.setenv("API_KEY", "test-secret-key")
    get_settings.cache_clear()

    response = client.post("/query", json={"question": "hello"})
    assert response.status_code == 401

    monkeypatch.setattr(main, "vector_db_ready", lambda _path: False)
    response = client.post(
        "/query",
        json={"question": "hello"},
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 503

    get_settings.cache_clear()


def test_health_is_public_without_api_key(client):
    response = client.get("/health")
    assert response.status_code == 200
