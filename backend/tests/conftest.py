"""Shared test setup. Tests run offline: no database, Redis or internet is needed.

The two connection URLs are required settings, so placeholder values are set before the
application is imported. Nothing connects to them: creating the SQLAlchemy engine does not
open a connection, and the health tests replace the real checks.

Safety: `DATABASE_URL` is always replaced by the placeholder unless it names the test database
(`matching_test`). A shell or container that has the development URL set can therefore never
point the application's engine at the development database while tests run.
"""

import os

from sqlalchemy.engine import make_url

TEST_DATABASE_NAME = "matching_test"  # the only database the integration tests may use
PLACEHOLDER_DATABASE_URL = "postgresql+psycopg://test:test@localhost:5432/test"


def _names_test_database(url: str | None) -> bool:
    try:
        return bool(url) and make_url(url).database == TEST_DATABASE_NAME
    except Exception:  # not a valid URL: treat it as unsafe
        return False


if not _names_test_database(os.environ.get("DATABASE_URL")):
    os.environ["DATABASE_URL"] = PLACEHOLDER_DATABASE_URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# Host names the fake DNS knows. Everything else resolves to a public documentation address.
FAKE_DNS = {
    "internal.jobs.example.com": ["10.0.0.8"],
    "metadata.example.com": ["169.254.169.254"],
    "mixed.example.com": ["93.184.216.34", "192.168.1.20"],
    "nowhere.invalid": None,
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """No test ever uses real DNS: the SSRF guard's resolver is replaced for every test."""
    from app.crawler import ssrf

    def resolve(host: str) -> list[str]:
        addresses = FAKE_DNS.get(host, ["93.184.216.34"])
        if addresses is None:
            raise ssrf.UnresolvableHostError(f"could not resolve {host}")
        return addresses

    monkeypatch.setattr(ssrf, "resolve_host", resolve)
