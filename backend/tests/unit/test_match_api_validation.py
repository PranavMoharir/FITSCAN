"""Invalid requests to the match routes get 422 before any database work (LLD §4.5, §9.2). Offline."""

import pytest


@pytest.mark.parametrize("path", ["/candidates/{id}/matches", "/jobs/{id}/matches"])
@pytest.mark.parametrize("limit", ["0", "11", "-1", "ten"])
def test_limit_out_of_range(client, path, limit):
    response = client.get(path.format(id="5b1e9c3a-2d4f-4a6b-8c7d-9e0f1a2b3c4d"), params={"limit": limit})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert [e["field"] for e in error["details"]["errors"]] == ["query.limit"]


@pytest.mark.parametrize("path", ["/candidates/not-a-uuid/matches", "/jobs/123/matches"])
def test_id_must_be_a_uuid(client, path):
    response = client.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["errors"][0]["field"].startswith("path.")


def test_match_routes_are_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/background-jobs/match"]
    assert "get" in paths["/candidates/{candidate_id}/matches"]
    assert "get" in paths["/jobs/{job_id}/matches"]
    assert paths["/background-jobs/match"]["post"].get("requestBody") is None  # no parameters
