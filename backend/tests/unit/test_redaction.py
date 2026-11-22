"""What the API shows of background-job logs, parameters and failure reasons (app/services/redaction.py).

The messages are real FITSCAN log lines (crawl, resume and match jobs). Progress must stay readable;
credentials, internal hosts, IP addresses, paths, stack traces, personal data and storage names must not
reach a browser.
"""

import pytest

from app.config import get_settings
from app.services.redaction import (
    DETAILS_REMOVED,
    EMAIL,
    INTERNAL_HOST,
    IP_ADDRESS,
    NUMBER,
    PATH,
    REDACTED,
    redact_context,
    redact_host,
    redact_params,
    redact_text,
    redact_url,
)

# --- Progress information stays as it is ------------------------------------------------------------

UNCHANGED = [
    "Crawl started: https://www.shopify.com/careers (max_depth 2, max_pages 10, allowed domains www.shopify.com)",
    "Crawl started: https://boards-api.greenhouse.io/v1/boards/codeforamerica/jobs?content=true (max_depth 1, "
    "max_pages 1, allowed domains boards-api.greenhouse.io)",
    "Loaded robots.txt for api.lever.co",
    "Fetched https://www.shopify.com/careers (200): 0 jobs extracted, 0 saved (0 new, 0 updated), 37 new links",
    "Ignored 18 links outside the allowed domains on https://www.shopify.com/careers",
    "Crawl finished: 10 pages processed (10 succeeded, 0 failed, 0 skipped), 255 discovered, 0 jobs extracted, 0 saved, 0 invalid",
    "HTTP 503 on attempt 2/3 for https://jobs.example.com/a, retrying in 2.4 s",
    "Rate limited (429) on https://api.lever.co/v0/postings/spotify?limit=10&mode=json, waiting 1.5 s (attempt 1/3)",
    "Failed https://jobs.example.com/old.html: HTTP 404",
    "Skipped https://jobs.example.com/admin: disallowed by robots.txt",
    "10 jobs saved by this crawl are new or changed in what matching reads. AUTO_REMATCH is off, so no match run "
    "was queued; recompute matches to include them.",
    "Resume parsing started: 1 file.",
    "Resume upload 9e8d7c6b: parsed (created a new candidate).",
    "Resume parsing finished: 1 of 1 files processed (1 new candidates, 0 updated, 0 duplicates skipped, 0 failed).",
    "Skill-like terms not in the taxonomy: 6 distinct terms, 6 occurrences (terms from resumes are not logged).",
    "Matching started: 9 candidates × 128 jobs (1152 pairs).",
    "Weights: required 70, nice-to-have 15, experience 10, location 5.",
    "Candidate 1a2b3c4d: scored against 128 jobs (best score 75.00).",
    "Saved 1152 matches for 9 candidates; computed at 2026-11-22T13:50:44.598726+00:00.",
    "Started automatically after crawl #5f4e3d2c saved new or changed jobs.",
    "Unexpected error during the crawl (OperationalError). Jobs saved so far are kept.",
    "Time limit exceeded; the crawl was stopped. Jobs saved so far are kept.",
]


@pytest.mark.parametrize("message", UNCHANGED)
def test_progress_messages_are_shown_unchanged(message):
    assert redact_text(message) == message


def test_public_urls_keep_their_path_and_harmless_query():
    for url in ("https://boards-api.greenhouse.io/v1/boards/codeforamerica/jobs?content=true",
                "https://api.lever.co/v0/postings/spotify?limit=10&mode=json",
                "https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html",
                "https://careers.example.com:8443/jobs/app/list"):
        assert redact_url(url) == url


# --- Internal hosts and IP addresses ---------------------------------------------------------------


def test_internal_hosts_are_replaced_in_crawl_messages():
    assert redact_text("Crawl started: http://mock-site:8080/static/index.html (max_depth 2, max_pages 30, "
                       "allowed domains mock-site)") == (
        f"Crawl started: http://{INTERNAL_HOST}/static/index.html (max_depth 2, max_pages 30, allowed domains {INTERNAL_HOST})")
    assert redact_text("Loaded robots.txt for mock-site") == f"Loaded robots.txt for {INTERNAL_HOST}"
    assert redact_text("Skipped http://mock-site:8080/private/internal.html: disallowed by robots.txt") == (
        f"Skipped http://{INTERNAL_HOST}/private/internal.html: disallowed by robots.txt")
    assert redact_text("All of db is treated as disallowed: robots.txt answered 500") == (
        f"All of {INTERNAL_HOST} is treated as disallowed: robots.txt answered 500")


def test_a_host_that_resolves_to_a_private_address_is_hidden_everywhere_in_the_message():
    shown = redact_text("Seed URL https://intranet.acme-corp.com/jobs cannot be crawled: "
                        "intranet.acme-corp.com resolves to a private or reserved address.")
    assert "intranet.acme-corp.com" not in shown
    assert shown == (f"Seed URL https://{INTERNAL_HOST}/jobs cannot be crawled: "
                     f"{INTERNAL_HOST} resolves to a private or reserved address.")


@pytest.mark.parametrize("host", ["localhost", "db", "redis", "printer.local", "build.internal", "nas.home.arpa",
                                  "nowhere.invalid", "wiki.corp"])
def test_internal_names_are_internal(host):
    assert redact_host(host) == INTERNAL_HOST
    assert INTERNAL_HOST in redact_text(f"Failed https://{host}/jobs: could not resolve {host}")
    assert host not in redact_text(f"Failed https://{host}/jobs: could not resolve {host}")


def test_the_crawlers_private_host_allow_list_is_internal(monkeypatch):
    monkeypatch.setattr(get_settings(), "crawler_private_host_allowlist", ["staging.jobs.example.org"])
    assert redact_url("http://staging.jobs.example.org/careers") == f"http://{INTERNAL_HOST}/careers"
    assert redact_text("Loaded robots.txt for staging.jobs.example.org") == f"Loaded robots.txt for {INTERNAL_HOST}"


def test_ip_addresses_are_replaced():
    assert redact_text("Failed http://10.0.0.8/jobs: timeout after 3 attempts") == (
        f"Failed http://{IP_ADDRESS}/jobs: timeout after 3 attempts")
    assert redact_text("connection to 93.184.216.34 and [2001:db8::1] refused") == (
        f"connection to {IP_ADDRESS} and {IP_ADDRESS} refused")
    assert redact_url("https://[2001:db8::7]:8443/jobs") == f"https://{IP_ADDRESS}/jobs"
    assert redact_text("computed at 2026-11-22T13:50:44+00:00 after 1.5 s") == "computed at 2026-11-22T13:50:44+00:00 after 1.5 s"


# --- Credentials and secrets ------------------------------------------------------------------------


def test_credentials_and_secret_query_values_never_reach_the_api():
    shown = redact_text("Seed URL https://admin:hunter2@jobs.example.com/feed?api_key=abc123&page=2#top "
                        "is not a valid http(s) URL.")
    assert "admin" not in shown and "hunter2" not in shown and "abc123" not in shown and "#top" not in shown
    assert shown == f"Seed URL https://jobs.example.com/feed?api_key={REDACTED}&page=2 is not a valid http(s) URL."
    for key in ("token", "access_token", "secret", "password", "signature", "session", "code"):
        assert redact_url(f"https://jobs.example.com/?{key}=s3cr3t&lang=en") == (
            f"https://jobs.example.com/?{key}={REDACTED}&lang=en")


def test_key_value_secrets_and_bearer_tokens_are_redacted():
    assert redact_text("login failed: password=hunter2 token: abc") == (
        f"login failed: password={REDACTED} token: {REDACTED}")
    assert redact_text("Authorization: Bearer eyJhbGciOi") == f"Authorization: {REDACTED}"
    assert redact_text("sent Bearer eyJhbGciOi to the API") == f"sent Bearer {REDACTED} to the API"


# --- Paths, stack traces, personal data -------------------------------------------------------------


def test_file_system_paths_are_replaced_but_url_paths_are_kept():
    assert redact_text("could not read /data/uploads/f00dbabe-b899.pdf") == f"could not read {PATH}"
    assert redact_text("browser missing at /ms-playwright/chromium-1248/chrome") == f"browser missing at {PATH}"
    assert redact_text(r"cannot open C:\Users\someone\Desktop\cv.pdf") == f"cannot open {PATH}"
    assert redact_text("Fetched https://example.org/app/jobs/data.html (200)") == "Fetched https://example.org/app/jobs/data.html (200)"


def test_stack_traces_and_extra_lines_are_removed():
    message = ('Unexpected failure\nTraceback (most recent call last):\n  File "/app/app/worker/tasks.py", line 140, in run\n'
               "ValueError: asha.verma@example.com")
    assert redact_text(message) == f"Unexpected failure {DETAILS_REMOVED}"
    assert redact_text('boom Traceback (most recent call last): File "/app/x.py", line 3') == f"boom {DETAILS_REMOVED}"
    assert redact_text("first line\nsecond line with details") == f"first line {DETAILS_REMOVED}"


def test_emails_and_phone_numbers_are_replaced():
    assert redact_text("contact asha.verma@example.com or +91 98765 43210") == f"contact {EMAIL} or {NUMBER}"
    assert redact_text("call 9876543210 now") == f"call {NUMBER} now"


# --- Structured context and job parameters -----------------------------------------------------------


def test_context_keeps_counts_shortens_ids_and_drops_storage_names():
    context = {"url": "http://mock-site:8080/static/jobs/a.html", "host": "mock-site", "depth": 2, "status": 200,
               "jobs_saved": 1, "rendered": False, "crawl_delay": 1.0, "attempt": 2,
               "candidate_id": "c0ffee01-1a2b-4c3d-8e4f-5a6b7c8d9e0f", "upload_id": "f00dbabe-2b3c-4d4e-9f5a-6b7c8d9e0f1a",
               "stored_file": "f00dbabe-2b3c-4d4e-9f5a-6b7c8d9e0f1a.pdf",
               "match_run_id": "d00dfeed-3c4d-4e5f-8a6b-7c8d9e0f1a2b", "warnings": 0}
    assert redact_context(context) == {
        "url": f"http://{INTERNAL_HOST}/static/jobs/a.html", "host": INTERNAL_HOST, "depth": 2, "status": 200,
        "jobs_saved": 1, "rendered": False, "crawl_delay": 1.0, "attempt": 2, "candidate_id": "c0ffee01",
        "upload_id": "f00dbabe", "match_run_id": "d00dfeed-3c4d-4e5f-8a6b-7c8d9e0f1a2b", "warnings": 0}
    assert redact_context(None) is None
    assert redact_context({"host": "api.lever.co", "crawl_delay": 1.0}) == {"host": "api.lever.co", "crawl_delay": 1.0}


def test_crawl_params_lose_credentials_and_internal_hosts():
    params = {"seed_url": "https://user:pw@mock-site:8080/static/index.html?token=x", "extractor": None,
              "max_depth": 2, "max_pages": 30, "allowed_domains": ["mock-site", "jobs.example.com", "10.1.2.3"]}
    assert redact_params("crawl", params) == {
        "seed_url": f"https://{INTERNAL_HOST}/static/index.html?token={REDACTED}", "extractor": None, "max_depth": 2,
        "max_pages": 30, "allowed_domains": [INTERNAL_HOST, "jobs.example.com", IP_ADDRESS]}
    public = {"seed_url": "https://api.lever.co/v0/postings/spotify?limit=10&mode=json", "extractor": None,
              "max_depth": 1, "max_pages": 1, "allowed_domains": ["api.lever.co"]}
    assert redact_params("crawl", public) == public


def test_resume_params_show_only_short_upload_references_and_sizes():
    params = {"files": [{"upload_id": "f00dbabe-2b3c-4d4e-9f5a-6b7c8d9e0f1a", "size_bytes": 154009,
                         "stored_file": "f00dbabe-2b3c-4d4e-9f5a-6b7c8d9e0f1a.pdf", "file": "Asha_Verma_CV.pdf"}]}
    assert redact_params("resume", params) == {"files": [{"upload_id": "f00dbabe", "size_bytes": 154009}]}


def test_match_params_are_shown_as_they_are():
    params = {"weights": {"required": 70, "nice": 15, "experience": 10, "location": 5},
              "after_crawl": "5f4e3d2c-0000-4000-8000-000000000001"}
    assert redact_params("match", params) == params
    assert redact_params("match", None) is None
