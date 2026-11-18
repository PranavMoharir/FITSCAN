"""Invalid requests to /background-jobs get 422 before any database work (LLD §9.2). Offline."""

import pytest

from app.config import get_settings

VALID = {"seed_url": "https://jobs.example.com/", "max_depth": 2, "max_pages": 50}


@pytest.fixture(autouse=True)
def _no_private_exceptions(monkeypatch):
    monkeypatch.setattr(get_settings(), "crawler_private_host_allowlist", [])
    monkeypatch.setattr(get_settings(), "crawler_max_pages_limit", 500)


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"seed_url": "ftp://jobs.example.com/"}, "body.seed_url"),
        ({"seed_url": "not a url"}, "body.seed_url"),
        ({"max_depth": 0}, "body.max_depth"),
        ({"max_depth": 11}, "body.max_depth"),
        ({"max_pages": 0}, "body.max_pages"),
        ({"max_pages": 501}, "body.max_pages"),
        ({"allowed_domains": ["https://jobs.example.com/path"]}, "body.allowed_domains"),
        ({"allowed_domains": []}, "body.allowed_domains"),
        ({"unexpected": True}, "body.unexpected"),
    ],
)
def test_malformed_crawl_requests(client, changes, field):
    response = client.post("/background-jobs/crawl", json={**VALID, **changes})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in [e["field"] for e in error["details"]["errors"]]


def test_missing_fields(client):
    response = client.post("/background-jobs/crawl", json={"seed_url": "https://jobs.example.com/"})
    fields = {e["field"] for e in response.json()["error"]["details"]["errors"]}
    assert response.status_code == 422 and fields == {"body.max_depth", "body.max_pages"}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"seed_url": "https://jobs.example.com/", "allowed_domains": ["other.example.org"]}, "not in allowed_domains"),
        ({"seed_url": "http://127.0.0.1:5432/"}, "private or reserved address"),
        ({"seed_url": "http://10.0.0.5/"}, "private or reserved address"),
        ({"seed_url": "http://169.254.169.254/latest/meta-data/"}, "private or reserved address"),
        ({"seed_url": "https://internal.jobs.example.com/"}, "private or reserved address"),
        ({"seed_url": "https://nowhere.invalid/"}, "does not resolve"),
        ({"extractor": "no_such_site"}, "unknown extractor"),
    ],
)
def test_seed_and_extractor_checks(client, changes, message):
    response = client.post("/background-jobs/crawl", json={**VALID, **changes})
    assert response.status_code == 422
    assert message in response.json()["error"]["details"]["errors"][0]["message"]


@pytest.mark.parametrize(
    "url",
    ["/background-jobs?status=paused", "/background-jobs?type=export", "/background-jobs?page=0",
     "/background-jobs?page_size=101", "/background-jobs/not-a-uuid",
     "/background-jobs/7f3c2a9e-1b44-4c55-9a51-0c9f3e7d2b10/logs?level=TRACE",
     "/background-jobs/7f3c2a9e-1b44-4c55-9a51-0c9f3e7d2b10/logs?after_id=-1"],
)
def test_invalid_query_and_path_values(client, url):
    response = client.get(url)
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_openapi_documents_the_background_job_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/background-jobs/crawl", "/background-jobs", "/background-jobs/{background_job_id}",
            "/background-jobs/{background_job_id}/cancel", "/background-jobs/{background_job_id}/logs"} <= set(paths)
