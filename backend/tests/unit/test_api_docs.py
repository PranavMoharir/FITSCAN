"""API_DOCS_ENABLED: the interactive documentation exists only when it is on (default), so a production
deployment (API_DOCS_ENABLED=false) does not publish a map of every endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

DOC_PATHS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]
REQUIRED = {"database_url": "postgresql+psycopg://u:p@db:5432/x", "redis_url": "redis://redis:6379/0"}


@pytest.fixture(autouse=True)
def default_environment(monkeypatch):
    """The 'default' cases must see the default, whatever the surrounding environment sets."""
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    monkeypatch.delenv("api_docs_enabled", raising=False)


def _client(**settings) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, **REQUIRED, **settings)))


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_are_served_by_default(path):
    """Local development is unchanged: every documentation path answers."""
    assert _client().get(path).status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_do_not_exist_when_disabled(path):
    response = _client(api_docs_enabled=False).get(path)
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}


def test_disabling_docs_keeps_every_api_route():
    """Only the documentation goes away. The schema is still built in memory (it is just not served),
    so its paths and methods list every API route of each app."""
    enabled = create_app(Settings(_env_file=None, **REQUIRED))
    disabled = create_app(Settings(_env_file=None, **REQUIRED, api_docs_enabled=False))

    def api_routes(app) -> set[tuple[str, str]]:
        return {(path, method) for path, operations in app.openapi()["paths"].items() for method in operations}

    assert len(api_routes(enabled)) >= 20
    assert api_routes(disabled) == api_routes(enabled)
    response = _client(api_docs_enabled=False).get("/sources")
    assert response.status_code == 200 and response.json()["items"]
