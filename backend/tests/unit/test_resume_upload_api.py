"""POST /background-jobs/resume: requests that fail before any job is created (LLD §4.5, §6.2, §9.2).

None of these touch the database. Accepted uploads (202) are tested in
tests/integration/test_resume_flow.py.
"""

import logging

import pytest

from app.config import get_settings
from tests import resume_pdfs


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    return tmp_path


def post(client, *files):
    return client.post("/background-jobs/resume", files=[("files", f) for f in files])


def test_no_acceptable_file_gives_422_with_every_reason_and_stores_nothing(client, upload_dir, caplog):
    caplog.set_level(logging.DEBUG)
    big = b"%PDF-1.7\n" + b"0" * (20 * 1024 * 1024)  # 20 MB + 9 bytes
    response = post(client, ("notes.txt", b"just some notes", "text/plain"), ("cv_09.pdf", big, "application/pdf"))
    assert response.status_code == 422
    assert response.json() == {"error": {
        "code": "NO_VALID_FILES", "message": "No file was accepted, so no job was created.",
        "details": {"rejected_files": [  # by position in the request: no file name is echoed back
            {"index": 0, "code": "NOT_A_PDF", "message": "File is not a PDF document."},
            {"index": 1, "code": "FILE_TOO_LARGE", "message": "File is larger than 20 MB."},
        ]}}}
    assert "notes" not in response.text and "cv_09" not in response.text
    assert list(upload_dir.iterdir()) == []
    assert not any("cv_09" in record.getMessage() or "notes.txt" in record.getMessage() for record in caplog.records)


def test_a_request_without_files_is_a_validation_error(client, upload_dir):
    response = client.post("/background-jobs/resume", data={"other": "x"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_ERROR" and body["details"]["errors"][0]["field"] == "body.files"


def test_more_files_than_the_limit_are_refused_as_a_whole(client, upload_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_files", 2)
    pdf = resume_pdfs.one_column()
    response = post(client, *[(f"cv_{i}.pdf", pdf, "application/pdf") for i in range(3)])
    assert response.status_code == 422
    assert response.json()["error"]["details"]["errors"] == [
        {"field": "body.files", "message": "at most 2 files per request (MAX_UPLOAD_FILES)"}]
    assert list(upload_dir.iterdir()) == []


def test_corrupt_and_encrypted_pdfs_pass_the_upload_check(client, upload_dir, monkeypatch):
    """They start with %PDF-, so they are accepted here and fail later, in the worker (LLD §4.5)."""
    from app.services import background_jobs as service

    created = {}

    def fake_enqueue(session, job):  # stop before the database
        created["params"] = job.params
        raise RuntimeError("stop here")
    monkeypatch.setattr(service, "_enqueue", fake_enqueue)
    with pytest.raises(RuntimeError, match="stop here"):
        post(client, ("broken.pdf", resume_pdfs.corrupt(), "application/pdf"),
             ("locked.pdf", resume_pdfs.encrypted(), "application/pdf"))
    files = created["params"]["files"]
    assert [set(f) for f in files] == [{"upload_id", "stored_file", "size_bytes"}] * 2  # no original names
    assert [f["stored_file"] for f in files] == [f"{f['upload_id']}.pdf" for f in files]
    assert "broken" not in str(created["params"]) and "locked" not in str(created["params"])
    assert list(upload_dir.iterdir()) == []  # the job was not created, so the stored files were removed again


def test_job_details_never_show_file_names_even_from_older_rows():
    """Rows written before names left the params are shown without them (defence in depth)."""
    import uuid

    from app.models import BackgroundJob
    from app.schemas.background_job import public_params

    upload_id = str(uuid.uuid4())
    old = BackgroundJob(type="resume", params={"files": [{"upload_id": upload_id, "file": "Asha_Verma_CV.pdf",
                                                          "size_bytes": 10}]})
    assert public_params(old) == {"files": [{"upload_id": upload_id[:8], "size_bytes": 10}]}
    crawl = BackgroundJob(type="crawl", params={"seed_url": "https://example.com/", "max_depth": 1})
    assert public_params(crawl) == crawl.params  # other job types are shown as they are


# --- Total size of one request (MAX_UPLOAD_REQUEST_MB) ---------------------------------------------


@pytest.fixture
def small_limits(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    monkeypatch.setattr(get_settings(), "max_upload_request_mb", 2)


TOO_LARGE = {"error": {"code": "VALIDATION_ERROR", "message": "The request is not valid.", "details": {"errors": [
    {"field": "body", "message": "the upload is larger than 2 MB in total (MAX_UPLOAD_REQUEST_MB); send fewer or smaller files"}]}}}


def test_a_request_over_the_total_limit_is_refused_before_reading(client, upload_dir, small_limits):
    part = b"%PDF-1.7\n" + b"0" * (900 * 1024)  # each file is under the 1 MB per-file limit
    response = post(client, *[(f"cv_{i}.pdf", part, "application/pdf") for i in range(3)])  # about 2.7 MB together
    assert response.status_code == 422 and response.json() == TOO_LARGE
    assert response.headers["connection"] == "close"  # the server does not keep reading the rest
    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


def test_a_streamed_request_without_content_length_stops_at_the_limit(upload_dir, small_limits):
    """Chunked upload, no Content-Length: the bytes are counted as they arrive and reading stops."""
    import asyncio

    import httpx

    from app.main import app

    chunk, sent = 64 * 1024, [0]

    async def body():
        yield (b'--b0undary\r\nContent-Disposition: form-data; name="files"; filename="big.pdf"\r\n'
               b"Content-Type: application/pdf\r\n\r\n%PDF-1.7\n")
        for _ in range(160):  # 10 MB, far over the limit
            sent[0] += chunk
            yield b"0" * chunk
        yield b"\r\n--b0undary--\r\n"

    async def upload():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            return await api.post("/background-jobs/resume", content=body(),
                                  headers={"Content-Type": "multipart/form-data; boundary=b0undary"})

    response = asyncio.run(upload())
    assert response.status_code == 422 and response.json() == TOO_LARGE
    assert response.headers["connection"] == "close"
    assert sent[0] <= 2 * 1024 * 1024 + chunk  # nothing was read after the limit
    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


def test_files_under_the_total_limit_still_get_per_file_checks(client, upload_dir, small_limits):
    response = post(client, ("big.pdf", b"%PDF-1.7\n" + b"0" * (1536 * 1024), "application/pdf"))  # 1.5 MB < 2 MB
    assert response.status_code == 422
    assert response.json()["error"]["details"]["rejected_files"][0]["code"] == "FILE_TOO_LARGE"


def test_the_total_limit_must_allow_one_file_of_the_largest_size():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="MAX_UPLOAD_REQUEST_MB must be larger than MAX_UPLOAD_MB"):
        Settings(database_url="postgresql://x", redis_url="redis://x", max_upload_mb=20, max_upload_request_mb=20)


def test_the_upload_is_documented_as_multipart(client):
    operation = client.get("/openapi.json").json()["paths"]["/background-jobs/resume"]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]
    assert {"202", "422", "503"} <= set(operation["responses"])
