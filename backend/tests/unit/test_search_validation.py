"""Invalid search, detail and export requests get 422 before any database work (LLD §4.4, §9.2). Offline."""

import pytest

from app.schemas.candidate import CandidateSearchParams
from app.schemas.job import JobSearchParams

UUID = "5b1e9c3a-2d4f-4a6b-8c7d-9e0f1a2b3c4d"


def fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    return [e["field"] for e in error["details"]["errors"]]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("sort=salary", "query.sort"),            # only allow-listed sort fields (LLD-5)
        ("sort=posted_date;drop table jobs", "query.sort"),
        ("order=up", "query.order"),
        ("page=0", "query.page"),
        ("page=-1", "query.page"),
        ("page=one", "query.page"),
        ("page_size=0", "query.page_size"),
        ("page_size=101", "query.page_size"),      # bounded maximum
        ("job_type=permanent", "query.job_type"),
        ("max_required_years=-1", "query.max_required_years"),
        ("max_required_years=51", "query.max_required_years"),
        ("max_required_years=three", "query.max_required_years"),
        ("max_required_years=nan", "query.max_required_years"),
        ("q=" + "x" * 201, "query.q"),
        ("company=acme", "query.company"),         # not a filter of the approved design
        ("remote=true", "query.remote"),
        ("listing=fake", "query.listing"),         # real or demo only
        ("listing=REAL", "query.listing"),
        ("industry=it", "query.industry"),         # industry codes only (software_it, healthcare, ...)
        ("industry=Healthcare", "query.industry"),
        ("source=indeed", "query.source"),         # only the sources of GET /sources
        ("export=all", "query.export"),
    ],
)
def test_invalid_job_search(client, query, field):
    assert field in fields(client.get(f"/jobs?{query}"))


@pytest.mark.parametrize("path", ["/jobs", "/exports/jobs?format=csv&"])
def test_new_job_filters_are_validated_in_search_and_export(client, path):
    separator = "&" if "?" in path else "?"
    query = f"{path}{separator}listing=maybe&industry=space&source=nope".replace("&&", "&")
    assert set(fields(client.get(query))) >= {"query.listing", "query.industry", "query.source"}


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("sort=email", "query.sort"),
        ("sort=posted_date", "query.sort"),        # a job sort field is not a candidate sort field
        ("order=sideways", "query.order"),
        ("page=0", "query.page"),
        ("page_size=1000", "query.page_size"),
        ("city=" + "x" * 201, "query.city"),
        ("min_years=3", "query.min_years"),        # LLD-6: /candidates has no experience filter
        ("location=pune", "query.location"),       # jobs say location, candidates say city
    ],
)
def test_invalid_candidate_search(client, query, field):
    assert field in fields(client.get(f"/candidates?{query}"))


@pytest.mark.parametrize("path", ["/jobs/not-a-uuid", "/jobs/123", "/candidates/xyz", "/candidates/1234"])
def test_detail_ids_must_be_uuids(client, path):
    assert fields(client.get(path))[0].startswith("path.")


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/exports/jobs", "query.format"),                     # format is required
        ("/exports/jobs?format=xml", "query.format"),
        ("/exports/jobs?format=csv&page=2", "query.page"),     # exports are not paged
        ("/exports/jobs?format=csv&sort=salary", "query.sort"),
        ("/exports/candidates?format=pdf", "query.format"),
        ("/exports/candidates?format=csv&location=pune", "query.location"),
        ("/exports/matches?format=csv&top=0", "query.top"),
        ("/exports/matches?format=csv&top=11", "query.top"),   # the top-10 limit
        ("/exports/matches?format=json&skill=" + "s" * 201, "query.skill"),
        ("/exports/matches?format=csv&job_type=full_time", "query.job_type"),
    ],
)
def test_invalid_exports(client, path, field):
    assert field in fields(client.get(path))


def _enum(schema: dict) -> list | None:
    """The allowed values of a parameter schema (a Literal, possibly optional)."""
    if "enum" in schema:
        return schema["enum"]
    for option in schema.get("anyOf", []):
        if "enum" in option:
            return option["enum"]
    return None


# The export parameters exactly as documented in LLD §4.7 and the README.
DOCUMENTED_EXPORTS = {
    "/exports/jobs": {
        "required": {"format"},
        "params": {"format", "q", "skill", "location", "job_type", "max_required_years", "listing", "industry", "source",
                   "sort", "order"},
        "sort": ["posted_date", "title"], "default_sort": "posted_date",
    },
    "/exports/candidates": {
        "required": {"format"}, "params": {"format", "q", "skill", "city", "sort", "order"},
        "sort": ["name", "years_experience"], "default_sort": "name",
    },
    "/exports/matches": {
        "required": {"format"}, "params": {"format", "q", "skill", "city", "sort", "order", "top"},
        "sort": ["name", "years_experience"], "default_sort": "name",
    },
}


@pytest.mark.parametrize("path", sorted(DOCUMENTED_EXPORTS))
def test_export_parameters_match_the_documentation(client, path):
    documented = DOCUMENTED_EXPORTS[path]
    parameters = {p["name"]: p for p in client.get("/openapi.json").json()["paths"][path]["get"]["parameters"]}
    assert set(parameters) == documented["params"]
    assert {name for name, p in parameters.items() if p.get("required")} == documented["required"]
    assert all(p["in"] == "query" for p in parameters.values())
    assert _enum(parameters["format"]["schema"]) == ["csv", "json"]
    assert _enum(parameters["sort"]["schema"]) == documented["sort"]
    assert parameters["sort"]["schema"]["default"] == documented["default_sort"]
    assert _enum(parameters["order"]["schema"]) == ["asc", "desc"]
    if "top" in parameters:
        top = parameters["top"]["schema"]
        assert (top["minimum"], top["maximum"], top["default"]) == (1, 10, 10)


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("format=csv&sort=posted_date", "query.sort"),   # a job sort field is not allowed for the match table
        ("format=csv&sort=score", "query.sort"),
        ("format=json&order=up", "query.order"),
        ("format=csv&page=1", "query.page"),
        ("format=csv&page_size=10", "query.page_size"),
        ("format=csv&location=pune", "query.location"),  # candidates are chosen by city, not location
    ],
)
def test_match_export_rejects_undocumented_values(client, query, field):
    assert field in fields(client.get(f"/exports/matches?{query}"))


def test_blank_filters_mean_no_filter():
    """A search box sends "" when it is empty; that must not filter for the empty string."""
    params = JobSearchParams(q="  ", skill="", location="\t")
    assert (params.q, params.skill, params.location) == (None, None, None)
    assert JobSearchParams(q="  python ").q == "python"
    assert CandidateSearchParams(city=" ").city is None


def test_defaults():
    jobs, candidates = JobSearchParams(), CandidateSearchParams()
    assert (jobs.sort, jobs.order, jobs.page, jobs.page_size) == ("posted_date", None, 1, 20)
    assert (candidates.sort, candidates.order, candidates.page, candidates.page_size) == ("name", None, 1, 20)


def test_new_routes_are_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in ["/jobs", "/jobs/{job_id}", "/candidates", "/candidates/{candidate_id}", "/skills",
                 "/exports/jobs", "/exports/candidates", "/exports/matches"]:
        operation = paths[path]["get"]
        assert operation["summary"] and "422" in operation["responses"] or path == "/skills", path
    assert "text/csv" in paths["/exports/matches"]["get"]["responses"]["200"]["content"]
    query = {p["name"] for p in paths["/jobs"]["get"]["parameters"]}
    assert query == {"q", "skill", "location", "job_type", "max_required_years", "listing", "industry", "source", "sort",
                     "order", "page", "page_size"}
    query = {p["name"] for p in paths["/candidates"]["get"]["parameters"]}
    assert query == {"q", "skill", "city", "sort", "order", "page", "page_size"}
