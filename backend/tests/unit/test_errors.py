"""Every error uses the envelope {"error": {"code", "message", "details"}} (HLD §12.1)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import AppError, register_error_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/items/{item_id}")
    def read_item(item_id: int) -> dict:
        if item_id == 404:
            raise AppError(404, "NOT_FOUND", "Item not found.")
        return {"item_id": item_id}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("secret internal detail")

    return app


def test_unknown_route_uses_envelope(client):
    response = client.get("/no-such-path")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found"}}


def test_wrong_method_uses_envelope(client):
    response = client.post("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_validation_error_uses_envelope_without_echoing_input():
    response = TestClient(_make_app()).get("/items/not-a-number")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["field"] == "path.item_id"
    assert "not-a-number" not in response.text


def test_app_error_uses_its_status_and_code():
    response = TestClient(_make_app()).get("/items/404")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Item not found."}}


def test_unexpected_error_hides_details():
    response = TestClient(_make_app(), raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}}
    assert "secret" not in response.text
