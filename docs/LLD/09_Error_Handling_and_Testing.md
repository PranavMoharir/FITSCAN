# 9. Error Handling and Testing

> **Status: Planned.** Error handling follows HLD §13.7, §14 and §15; testing follows HLD §18. No tests exist yet, because no application code exists.

## 9.1 Principles

1. **Validate early, in three layers.** Pydantic checks every API input and every extracted record. Normalization functions clean dates, numbers, URLs and text before validation. Database constraints (NOT NULL, CHECK, UNIQUE, FOREIGN KEY) are the final safety net.
2. **Fail small.** An error affects only the smallest unit: one page, one file or one record. It is logged, counted, and the job continues.
3. **Clear messages, no internals.** Users see actionable messages in the standard error envelope (Part 4, Section 4.4). Stack traces and internal paths go only to server logs.
4. **No personal data in logs.** Logs contain URLs, upload IDs, page numbers and reasons, never uploaded file names, resume content or personal data. Exception messages are not logged for resume files either (a database error can quote rejected values): only the exception type and code location.

## 9.2 Invalid Inputs (API)

| Input problem | Response |
|---|---|
| Malformed crawl request: not an http(s) URL, limits out of range, seed outside the allow-list, seed resolving to a private address | 422 with field details; no job is created |
| Out-of-range `page`, `page_size` or `limit` | 422 (each has a bounded maximum) |
| Unknown job, candidate or background-job ID | 404 |
| Cancelling a job that has already finished | 409 |
| Uploaded file over 20 MB, or not a PDF | That file is rejected with `FILE_TOO_LARGE` or `NOT_A_PDF`; the other files are still accepted (202) |
| No acceptable file in an upload | No job is created: 422 with code `NO_VALID_FILES` and every file's reason in `details.rejected_files` (Section 4.5) |
| No files, or more files than the per-request limit | 422 |
| All files of one upload together larger than `MAX_UPLOAD_REQUEST_MB` | 422 `VALIDATION_ERROR`, decided while the request streams in: nothing is stored, no job is created, and the connection is closed (Section 4.5) |
| `sort` or `order` value not in the allow-list | 422: only allow-listed sort fields reach the query, so user input never becomes SQL |

## 9.3 Failed PDFs

Each file is handled separately, so one bad file never stops the others (Part 6).

| Problem | Detected by | Result shown to the user |
|---|---|---|
| Corrupt file | `%PDF-` check (API) or PyMuPDF failing to open it (worker) | "cv_07.pdf failed: the file is damaged or not a valid PDF." |
| Encrypted file | PyMuPDF `is_encrypted` / `needs_pass` | "cv_08.pdf failed: the file is password-protected." |
| Scanned file that OCR cannot read | Tesseract missing, timing out or returning no text | The file is flagged with a WARNING ("scanned resume: OCR produced no text"); no empty candidate is created |
| Invalid optional field (for example a malformed email) | Pydantic `CandidateRecord` | The field is set to null and noted in `parse_warnings`; the candidate is still saved and the page shows a warning |
| Same file uploaded again | Same SHA-256 hash | Logged as "duplicate file, skipped" |

## 9.4 Crawler Errors

| Problem | Handling | Visible as |
|---|---|---|
| Network timeout or connection error | Retry with exponential backoff and jitter; after the last attempt, mark the page failed and continue | A WARNING per retry, then an ERROR; failed-page count |
| HTTP 429 | Wait for `Retry-After` (capped) or back off; slow down that domain for the rest of the crawl | WARNING "Rate limited (429), waiting N s" |
| HTTP 5xx | Retry with backoff, then skip | WARNING, then ERROR |
| HTTP 404 or other 4xx | No retry; skip | Log line |
| Page disallowed by robots.txt | Not fetched. If the **seed** is disallowed, the job fails at once. | INFO "Skipped … disallowed by robots.txt" |
| Invalid or non-allowed link found on a page | Dropped silently | DEBUG log |
| Malformed HTML, or the extractor raises an error | Caught for that page only; the page counts as failed | WARNING "Could not extract from …" |
| A job record fails validation | Only that record is skipped | WARNING log |
| JavaScript page does not render (Playwright timeout) | Treated like a network failure: retried, then skipped | WARNING, then ERROR |
| Duplicate job | The upsert merges it into the existing row | DEBUG or INFO "Updated existing job" |

**Why one bad page never crashes a crawl:** the crawl loop handles one URL per iteration inside a `try/except`. Fetch, parse and validation errors for that URL become a log line and a counter, and the loop moves on. Only problems that make the whole crawl impossible end the job as `failed`: an invalid or disallowed seed, or a lost database connection.

## 9.5 Background Task and Infrastructure Failures

The state rules are in Part 5, Section 5.8. What the user sees:

| Failure | Handling | Visible as |
|---|---|---|
| Every item failed | Job `failed` with "all N items failed" | Status badge and reason |
| Job-level error | Job `failed` with `error_message` | Status and reason on the detail page |
| Time limit exceeded | Job `failed` with "time limit exceeded"; partial results kept | Status and reason |
| Worker stopped (killed, out of memory) | No heartbeat for `JOB_HEARTBEAT_TIMEOUT_SECONDS` (default 10 minutes), so the stale-job check marks the job `failed` ("worker stopped unexpectedly"); partial results kept; the user can start a new job | Status and reason |
| Job never picked up (Redis lost the message, or no worker is running) | Queued for longer than `JOB_QUEUED_TIMEOUT_SECONDS` (default 10 minutes) with no heartbeat from any job, so the stale-job check marks it `failed` (Section 5.8) | Status and reason "No worker picked up this job within 10 minutes. The worker may be stopped, or the task was lost. Start it again." |
| Redis unavailable when a job is created | Job marked `failed` ("could not be queued"); API returns 503 | Error toast |
| Database unavailable | API returns 503 "Service temporarily unavailable"; the worker retries briefly, then fails the job if it can still write, or leaves it to the heartbeat check; `/health` reports the database as down | Error toast; failed job |

## 9.6 Testing Approach

- **Pytest** for everything.
- **No internet in tests** (brief requirement). HTTP is replaced by httpx's `MockTransport`, which serves saved pages. Pages and PDFs come from fixtures in `backend/tests/fixtures/`.
- Pure functions (URL normalization, skill extraction, scoring) are tested directly. Integration tests check that the parts work together.
- Rate-limit and backoff tests use a fake clock or zero delays, so they run instantly.

**Fixtures:**

| Folder | Contents |
|---|---|
| `fixtures/html/` | Saved pages per site: `<site>_listing.html`, `<site>_detail.html`, and `<site>_rendered.html` for a JavaScript page captured after rendering |
| `tests/resume_pdfs.py` | One-column, two-column, skills-in-a-table, scanned (image only), encrypted and corrupt resumes, generated with PyMuPDF while the tests run, so no PDF files are committed and no extra library is needed. Every person in them is invented. |
| Labelled examples | Job and resume texts with hand-labelled expected skills, for precision and recall (Part 6, Section 6.9) |

## 9.7 Unit Tests

| Area | Important scenarios |
|---|---|
| Extractors | Each saved page gives the expected job records and links; malformed HTML does not crash; the JavaScript extractor parses its rendered snapshot; the Greenhouse and Lever API fixtures and a career page with JobPosting data give every field they publish, missing fields stay unknown, broken bodies fail only their page; JSON reaches only JSON extractors; robots.txt still stops a job board; jobs on a demo host are dropped unless its demo extractor finds them |
| Industries | Labelled examples from every industry (most of them non-IT); unknown, weak and tied evidence stay Other / Unclassified; the points and caps; the explanations; the rules file checks; the non-IT skills and the ambiguous words that must not become skills |
| Crawler | BFS order; stops at `max_depth` and `max_pages`; URL normalization cases (Part 5, Section 5.11); each URL fetched once; allow-list; robots.txt allow and deny; retries on timeout, 429 (with `Retry-After`) and 5xx; no retry on 404; one failing page does not stop the crawl; SSRF guard; cancellation |
| Resume parsing | Fields from one-column, two-column and skills-in-table resumes; two-column text keeps the left column before the right; years of experience from overlapping date ranges, including "Present", computed against a fixed "today" passed in by the test; scanned-page detection; encrypted and corrupt files give the expected messages; non-PDF and oversized files are rejected |
| OCR | The scanned fixture yields text and `parsed_with_ocr = true`. Skipped automatically if the Tesseract binary is missing (it is present in the worker image). |
| Skill extraction | "JS" → JavaScript and "ReactJS" → React; longest match; "java" not found inside "javascript"; `C++`, `C#`, `.NET`; ambiguous words only in skill context; "R&D" and "go-to-market" rejected; required versus nice-to-have splitting, including "Docker is a plus"; precision and recall on the labelled examples |
| Matching | The worked example; a perfect match scores 100; no overlap; every edge case in Part 7, Section 7.5; clamping; deterministic tie-breaking; the explanation agrees with the breakdown |

**Score-precision tests.** These four tests check that rounding happens only for display and never affects ranking (Part 7, Section 7.6):

1. **Different scores that display the same.** Scores 80.004 and 80.001 both display as 80.00. The 80.004 match ranks first, even when the other has the higher text similarity.
2. **Top-10 boundary.** A candidate has 11 matches, and the 10th and 11th scores differ only after the second decimal place. The top 10 contains the higher one.
3. **Equal scores from different components.** The worked example and the second 71⅔ job from Part 7, Section 7.6 are stored with identical values, so text similarity decides their order.
4. **Stored versus shown.** The stored score is unrounded; the API, the explanation and exports show exactly 2 decimals; `rank` follows the full-precision order.

## 9.8 API and Integration Tests

| Kind | What is tested | How |
|---|---|---|
| API | 422 on invalid input; 202 when creating jobs; upload status rule (202 with some rejected files; 422 `NO_VALID_FILES` with every file's reason when none is accepted); cancel answers 200, 202 or 409 as in Section 5.7; logs with `after_id`; search filters, `max_required_years` (including jobs with no minimum), sorting (allowed fields, 422 for others, missing values last) and pagination; match endpoints return at most 10 results in ranking order; the match export honours the candidate filters; `/skills` returns the standard list shape with every skill on one page; `/health` returns 200, and 503 when the database or Redis is down or does not answer within its short timeout; export content types, headers and CSV formula-injection protection; the error envelope | FastAPI `TestClient` with a test PostgreSQL database; Celery publishing replaced by a stub that records calls |
| Stale-job check | A `running` job with an old heartbeat becomes `failed`; a `queued` job past the timeout becomes `failed` only when no job has a recent heartbeat; a queued job waiting behind a running job is left alone; a match job about to do its final write is not failed, because it wrote a heartbeat just before; running the check twice changes nothing more | Test database with rows whose timestamps are set in the past |
| Integration | Upload → resume task → candidate saved; crawl task against the mock transport → jobs saved; match task → top-10 endpoints return the expected order | Tasks called directly (or with Celery's eager mode) against the test database |
| Real sources | Greenhouse, Lever and career-page fixtures crawled through the API: fields, industries, real listings, original posting and source URL; re-crawls and duplicate postings give no duplicates; real and demo jobs side by side with the `listing`, `industry` and `source` filters; exports keep the source columns; one matching engine for both kinds (every stored score equals the scoring function); demo hosts refused for real-source extractors; the industry migration classifies existing jobs and changes nothing else | The real `crawl` and `match` tasks against the test database |
| Automatic re-matching | Change detection for each value matching reads and for the columns it never reads; a crawl that saves new or changed jobs queues one match run with the active weights and `after_crawl`; nothing after an unchanged re-crawl, a cancelled crawl, with no candidates or with `AUTO_REMATCH=false`; a failed crawl that saved jobs still queues one; no second run while one is queued or for the same crawl; concurrent requests are decided one at a time under the lock; a broker failure leaves the crawl's status unchanged; an automatic run never overwrites a newer run's results | The real `crawl` task against a fake job board; `match` publishing recorded, runs started on purpose; threads for the concurrent cases |

**Continuous integration.** `.github/workflows/ci.yml` runs every test above on each push and pull request to `main`: the backend job with Tesseract and a throwaway PostgreSQL service whose only database is `matching_test` (it confirms `current_database()` first and fails if any test is skipped), and the frontend job with `npm ci` and `npm run build`. It needs no secrets and reaches no real database, broker, job site or browser.

## 9.9 Manual Checks

- **5-candidate hand check** (brief deliverable). The README checks whether the top 3 jobs of five candidates make sense. Any skill-extraction error it finds becomes a new labelled test case.
- **Demo video.** It includes one handled failure, for example an encrypted PDF or a page that times out.
