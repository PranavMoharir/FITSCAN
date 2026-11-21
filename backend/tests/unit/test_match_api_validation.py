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
    assert "get" in paths["/matching/weights"]
    body = paths["/background-jobs/match"]["post"]["requestBody"]
    assert not body.get("required", False)  # optional: without a body the run uses the active weights


# --- Weights sent with a match run (LLD §7.4): whole numbers 0-100, total exactly 100 ----------------

VALID = {"required": 70, "nice": 15, "experience": 10, "location": 5}


@pytest.mark.parametrize(("body", "field"), [
    ({"weights": {"required": 70, "nice": 15, "experience": 10}}, "body.weights.location"),           # missing
    ({"weights": {**VALID, "location": -5, "required": 80}}, "body.weights.location"),                  # negative
    ({"weights": {"required": 101, "nice": 0, "experience": 0, "location": 0}}, "body.weights.required"),  # above 100
    ({"weights": {**VALID, "location": 4}}, "body.weights"),                                             # total 99
    ({"weights": {**VALID, "location": 6}}, "body.weights"),                                             # total 101
    ({"weights": {**VALID, "required": 69.5, "location": 5.5}}, "body.weights.required"),               # decimals
    ({"weights": {**VALID, "required": 70.0}}, "body.weights.required"),                                # 70.0 is not whole
    ({"weights": {**VALID, "required": "70"}}, "body.weights.required"),                                # a string
    ({"weights": {"required": True, "nice": 15, "experience": 10, "location": 74}}, "body.weights.required"),  # a bool
    ({"weights": {**VALID, "bonus": 0}}, "body.weights.bonus"),                                         # unknown key
    ({"weights": VALID, "extra": 1}, "body.extra"),                                                     # unknown field
    ({"weights": [70, 15, 10, 5]}, "body.weights"),                                                     # not an object
])
def test_invalid_weights_are_refused_before_any_database_work(client, body, field):
    response = client.post("/background-jobs/match", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in [e["field"] for e in error["details"]["errors"]], error["details"]


def test_a_wrong_total_is_explained_never_rescaled(client):
    response = client.post("/background-jobs/match", json={"weights": {**VALID, "location": 4}})
    (error,) = response.json()["error"]["details"]["errors"]
    assert error == {"field": "body.weights", "message": "Value error, the weights must add up to 100, so scores stay on a 0-100 scale"}


@pytest.mark.parametrize(("params", "expected"), [
    (None, None),                                                             # a run from before weights were recorded
    ({}, None),
    ({"weights": VALID}, VALID),
    ({"weights": {"required": 33.3, "nice": 33.3, "experience": 33.4, "location": 0}},  # MATCH_WEIGHTS may be decimal
     {"required": 33.3, "nice": 33.3, "experience": 33.4, "location": 0}),
    ({"weights": {**VALID, "location": 4}}, None),                            # does not add up to 100
    ({"weights": {**VALID, "location": True}}, None),
    ({"weights": {"required": 70, "nice": 15, "experience": 15}}, None),
    ({"weights": [70, 15, 10, 5]}, None),
])
def test_recorded_weights(params, expected):
    from app.services.background_jobs import recorded_weights

    assert recorded_weights(params) == expected
