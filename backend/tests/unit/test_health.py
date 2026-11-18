"""GET /health returns 200 when both checks pass, otherwise 503 in the error envelope (LLD-3)."""

import time

import pytest

from app.api import health


def _set_checks(monkeypatch: pytest.MonkeyPatch, database_ok: bool, redis_ok: bool) -> None:
    monkeypatch.setattr(health, "check_database", lambda: database_ok)
    monkeypatch.setattr(health, "check_redis", lambda: redis_ok)


def test_health_ok(client, monkeypatch):
    _set_checks(monkeypatch, database_ok=True, redis_ok=True)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}


@pytest.mark.parametrize(
    ("database_ok", "redis_ok", "expected_details"),
    [
        (True, False, {"database": "ok", "redis": "down"}),
        (False, True, {"database": "down", "redis": "ok"}),
        (False, False, {"database": "down", "redis": "down"}),
    ],
)
def test_health_unavailable(client, monkeypatch, database_ok, redis_ok, expected_details):
    _set_checks(monkeypatch, database_ok, redis_ok)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Service temporarily unavailable.",
            "details": expected_details,
        }
    }


def test_slow_check_is_cut_off_at_the_deadline(client, monkeypatch):
    # Both checks run at the same time; one that is still running at the deadline counts as down.
    monkeypatch.setattr(health, "HEALTH_CHECK_DEADLINE_SECONDS", 0.3)
    monkeypatch.setattr(health, "check_database", lambda: time.sleep(0.2) or True)
    monkeypatch.setattr(health, "check_redis", lambda: time.sleep(2) or True)
    started = time.perf_counter()
    response = client.get("/health")
    elapsed = time.perf_counter() - started
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"database": "ok", "redis": "down"}
    assert elapsed < 1.0  # well below the slow check's 2 s


def test_check_that_raises_counts_as_down(client, monkeypatch):
    def broken() -> bool:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(health, "check_database", broken)
    monkeypatch.setattr(health, "check_redis", lambda: True)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"database": "down", "redis": "ok"}


def test_redis_check_returns_false_when_unreachable(monkeypatch):
    # Port 1 on localhost refuses connections immediately, so this stays fast and offline.
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")
    assert health.check_redis() is False


def test_cors_allows_only_the_configured_origin(client, monkeypatch):
    _set_checks(monkeypatch, database_ok=True, redis_ok=True)
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    other = client.get("/health", headers={"Origin": "http://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in other.headers
