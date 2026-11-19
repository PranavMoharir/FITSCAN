"""Settings are read from environment variables and validated (HLD §16.3).

Every test here starts from an EMPTY settings environment: `Settings` reads each field from the
process environment as well as from `.env`, and Docker Compose passes the whole `.env` into the
containers (for example CRAWLER_PRIVATE_HOST_ALLOWLIST=mock-site). Without the clean-up, the
"defaults" test would check the container's configuration instead of the defaults, and pass or
fail depending on where it runs.
"""

import os

import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED = {"DATABASE_URL": "postgresql+psycopg://u:p@db:5432/x", "REDIS_URL": "redis://redis:6379/0"}


def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every environment variable that Settings would read (names are case-insensitive)."""
    for name in list(os.environ):
        if name.lower() in Settings.model_fields:
            monkeypatch.delenv(name)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Settings from exactly REQUIRED + `env`: no process variables and no developer .env file."""
    _clean_environment(monkeypatch)
    for name, value in {**REQUIRED, **env}.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_settings_tests_ignore_the_surrounding_environment(monkeypatch):
    """The worker container's environment (from Compose) must not leak into the settings tests."""
    monkeypatch.setenv("CRAWLER_PRIVATE_HOST_ALLOWLIST", "mock-site")
    monkeypatch.setenv("max_upload_mb", "99")  # any letter case is read by pydantic-settings
    monkeypatch.setenv("UNRELATED_VARIABLE", "kept")
    s = _settings(monkeypatch)
    assert s.crawler_private_host_allowlist == []
    assert s.max_upload_mb == 20
    assert os.environ["UNRELATED_VARIABLE"] == "kept"


def test_defaults_match_the_design(monkeypatch):
    s = _settings(monkeypatch)
    assert s.max_upload_mb == 20
    assert (s.match_weights.required, s.match_weights.nice, s.match_weights.experience, s.match_weights.location) == (
        70,
        15,
        10,
        5,
    )
    assert s.job_heartbeat_timeout_seconds == 600
    assert s.job_queued_timeout_seconds == 600
    assert s.crawler_private_host_allowlist == []


def test_connection_urls_are_required(monkeypatch):
    _clean_environment(monkeypatch)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    missing = {err["loc"][0] for err in excinfo.value.errors()}
    assert missing == {"database_url", "redis_url"}


def test_comma_separated_lists(monkeypatch):
    s = _settings(
        monkeypatch,
        CORS_ORIGINS="http://localhost:5173, http://127.0.0.1:5173",
        CRAWLER_PRIVATE_HOST_ALLOWLIST="mock-site",
    )
    assert s.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert s.crawler_private_host_allowlist == ["mock-site"]


def test_match_weights_from_env(monkeypatch):
    s = _settings(monkeypatch, MATCH_WEIGHTS="60,20,15,5")
    assert s.match_weights.required == 60
    assert s.match_weights.location == 5


@pytest.mark.parametrize("value", ["70,15,10", "70,15,10,10", "70,15,20,-5", "a,b,c,d"])
def test_invalid_match_weights_are_rejected(monkeypatch, value):
    with pytest.raises(ValidationError):
        _settings(monkeypatch, MATCH_WEIGHTS=value)
