# FITSCAN: Job–Candidate Matching Platform

A platform that collects job openings by crawling, reads candidate resumes from PDFs, and matches each candidate to the jobs that fit best (and each job to its best candidates). Crawling, parsing and matching run as background jobs; users watch progress, browse results and export CSV or JSON.

The design is in [`docs/`](docs/): the [detailed HLD](docs/HLD_Job_Candidate_Matching_Platform_Full.md), the [LLD](docs/LLD/README.md) and the [architecture decisions](docs/ARCHITECTURE_DECISIONS.md). Data sources: [`DATA_SOURCES.md`](DATA_SOURCES.md). How AI was used: [`AI_USAGE.md`](AI_USAGE.md). Sample outputs (synthetic data only): [`samples/`](samples/). Demo video plan: [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md).

**Live demo:** <https://fitscan-demo.duckdns.org> (the application is at `/app`). It is password-protected; the login is shared separately, never in this repository. It holds synthetic data only. The submission summary for reviewers is [`SUBMISSION.md`](SUBMISSION.md).

**Stack:**
- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy 2 and Alembic on PostgreSQL 17; Celery workers with Redis as the broker.
- Crawling, parsing and matching: httpx and Playwright (headless Chromium); PyMuPDF, pdfplumber and Tesseract OCR; a weighted scoring formula, with scikit-learn TF-IDF used only to order exactly equal scores.
- Frontend: React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui (Radix UI), lucide-react, React Router and Framer Motion.
- Deployment: Docker Compose (API, worker, PostgreSQL, Redis, frontend and an optional mock job site); in production, a Caddy HTTPS proxy in front, on an Oracle Cloud Always Free VM.

## Status

**Phases 1–8 done (final):** project setup, database, background jobs with the job crawler, resume upload with PDF parsing and OCR, the matching engine, the search, detail and export API, the public landing page and the application UI, plus three of the brief's optional features (adjustable scoring weights, automatic re-matching after crawls and a CI pipeline) and real job sources across industries next to the demo sites. Crawls, resume parsing and match runs happen in the Celery worker; their status, progress, logs, jobs, candidates and matches are stored in PostgreSQL.

| Works now | Not done |
|---|---|
| `docker compose up` starts the API, worker, PostgreSQL, Redis, UI and the mock job site; every service has a health check | Demo video: not recorded yet (plan: [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md)) |
| The eight tables of [LLD Part 3](docs/LLD/03_Database_Design.md) (SQLAlchemy models + Alembic migration) | Deferred optional features: resuming an interrupted crawl, and embedding-based (semantic) matching |
| Background jobs: create a crawl, resume or match job, list, detail, logs, cancel; heartbeats and stale-job checks | User accounts and authentication (out of scope; see [Security controls](#security-controls)) |
| Polite BFS crawler: robots.txt, rate limit, retries, SSRF guard, Playwright only when needed | |
| Extractors: Fake Python Jobs, the mock site (static and JavaScript), generic JSON-LD | |
| Real job sources: company career pages (schema.org `JobPosting`), Greenhouse and Lever job boards (public APIs); demo sites stay and are always labelled demo ([`DATA_SOURCES.md`](DATA_SOURCES.md)) | |
| Industries: every job is classified (12 industries, or Other / Unclassified) with the evidence shown; filters for real or demo listings, industry and source | |
| Local verification (22 November 2026, not on the live demo): a Greenhouse board (10 jobs) and a Lever board (10 jobs) crawled into the running local stack; real/demo labels, industries, original-posting links and `AUTO_REMATCH=false` confirmed ([`DATA_SOURCES.md`](DATA_SOURCES.md)) | |
| Job validation, de-duplication (upsert by `dedup_key`), skills taxonomy and job skills | |
| Resume upload: size and `%PDF-` checks per file, UUID storage, one background job per upload | |
| PDF parsing: one- and two-column layouts, tables, garbled text, OCR of scanned pages (Tesseract) | |
| Candidate fields, skills, validation, de-duplication (same file skipped, same email updated) | |
| Matching: every candidate against every job, exact scores, explanations, TF-IDF tie-breaker; top 10 in both directions | |
| Adjustable scoring weights: each match run takes optional whole-number weights that add up to 100 and records them; `GET /matching/weights` | |
| Automatic re-matching: a crawl that saved new jobs, or changed what matching reads from a job, queues a match run (`AUTO_REMATCH`) | |
| Continuous integration: GitHub Actions runs every backend test (with PostgreSQL and Tesseract) and the frontend build on each push and pull request to `main` | |
| Search and detail: `GET /jobs`, `/jobs/{id}`, `/candidates`, `/candidates/{id}`, `/skills`; filters, sorting, paging | |
| Exports: jobs, candidates and the match table as CSV or JSON, streamed, with formula-injection protection | |
| `GET /health`, OpenAPI docs at `/docs` (switched off in production with `API_DOCS_ENABLED=false`), one error envelope for every error | |
| Public deployment, live since 23 November 2026 at <https://fitscan-demo.duckdns.org>: a production Compose override with a Caddy proxy (HTTPS, password, rate and size limits, security headers) on an Oracle Cloud Always Free VM, with daily verified database backups ([Deploy publicly](#deploy-publicly)) | |
| Frontend: public landing page at `/` (sample data only, no API calls) and the application at `/app` (dashboard, background jobs, jobs, candidates, matching, skills, exports) | |
| Sample outputs in [`samples/`](samples/): the demo jobs, the 5 synthetic candidates and their top-10 match table, as CSV and JSON | |

Also in this README: [architecture and design decisions](#architecture-and-design-decisions), [how matching works](#how-matching-works), the [hand check of 5 candidates](#matching-hand-check-5-candidates), [known limitations](#known-limitations) and [time spent](#time-spent).

## Quick start (Docker)

Requires Docker Desktop (or Docker Engine with Compose v2). Get the code with `git clone https://github.com/PranavMoharir/FITSCAN.git`. Then, in the `FITSCAN` folder, setup is two commands:

```bash
cp .env.example .env
docker compose up --build
```

| URL | What it is |
|---|---|
| http://localhost:5173 | Web UI: the FITSCAN landing page; the application starts at `/app` |
| http://localhost:8000/docs | Interactive API documentation |
| http://localhost:8000/health | Health check: `{"status": "ok", "database": "ok", "redis": "ok"}` |

`.env.example` works as it is for local use. Change `POSTGRES_PASSWORD` (and the same password in `DATABASE_URL`) if the machine is shared.

Stop with `Ctrl+C`, or `docker compose down`. Data is kept in Docker volumes; `docker compose down -v` deletes it. The first build takes several minutes, because the worker image downloads headless Chromium.

A new installation starts with an empty database. To see matches, crawl jobs, upload resumes and compute matches, in that order: in the UI with **New crawl**, **Upload resumes** and **Recompute matches**, or with the requests in the next sections. To see example results without running anything, open [`samples/`](samples/).

### Start a crawl

Crawl the bundled mock site: static pages and one JavaScript-rendered page.

```bash
curl -X POST http://localhost:8000/background-jobs/crawl -H "Content-Type: application/json" \
     -d '{"seed_url": "http://mock-site:8080/static/index.html", "max_depth": 2, "max_pages": 30}'
```

The answer is `202 Accepted` with a `background_job_id`. Follow it with:

| Request | Shows |
|---|---|
| `GET /background-jobs` | All jobs, newest first (`?type=crawl&status=running&page=1&page_size=20`) |
| `GET /background-jobs/{id}` | Status, progress, counters, parameters, failure reason |
| `GET /background-jobs/{id}/logs?after_id=0&level=INFO` | Timestamped log lines; pass the last `next_after_id` to get only new ones |
| `POST /background-jobs/{id}/cancel` | 200 for a queued job, 202 for a running job (it stops after the current page), 409 if already finished |

A real job source works the same way. A Greenhouse or Lever board needs one request, to its public API:

```bash
curl -X POST http://localhost:8000/background-jobs/crawl -H "Content-Type: application/json" \
     -d '{"seed_url": "https://boards-api.greenhouse.io/v1/boards/<board token>/jobs?content=true", "max_depth": 1, "max_pages": 1}'
```

`GET /sources` lists every supported source (real ones first, then the demo sites) and how to build its seed URL; the UI's "New crawl" dialog offers them by name. [`DATA_SOURCES.md`](DATA_SOURCES.md) says what each source gives, its terms and its limits. Crawl only sites you may crawl: robots.txt, the allowed hosts and the private-address guard apply to every source, and FITSCAN never logs in or gets around access controls. The crawled jobs are in the `jobs` table, and their skills in `job_skills`.

### Upload resumes

Send one or more PDFs as `files` (at most `MAX_UPLOAD_FILES` per request, each at most `MAX_UPLOAD_MB`, all together at most `MAX_UPLOAD_REQUEST_MB`):

```bash
curl -X POST http://localhost:8000/background-jobs/resume -F "files=@cv_01.pdf" -F "files=@cv_02.pdf"
```

The answer is `202 Accepted` with the new `resume` job, `accepted_files` (`index`, `upload_id`, `size_bytes`) and `rejected_files` (`index`, `code` `FILE_TOO_LARGE` or `NOT_A_PDF`, `message`). `index` is the file's 0-based position in the request; no response ever repeats a file name. If no file is accepted, the answer is `422` with code `NO_VALID_FILES`, every file's reason, and no job. Follow the job with the same `/background-jobs/{id}` and `/logs` requests as a crawl; it processes one file at a time and can be cancelled between files. Parsed candidates are in the `candidates` table, and their skills in `candidate_skills`.

To try it with synthetic resumes (one column, two columns, a skills table, a scanned page, an encrypted and a corrupt file), generate them from `backend/` with `python -m tests.resume_pdfs sample-resumes`.

### Clean up old uploads

Uploaded PDFs are personal data. A manual command removes the ones no longer needed; it is a dry run unless `--delete` is given, prints counts only, and runs in the API container (the worker's view of the uploads is read-only):

```bash
docker compose exec api python -m app.services.upload_retention            # dry run
docker compose exec api python -m app.services.upload_retention --delete   # delete
```

| Upload | What happens |
|---|---|
| Its job is queued or running | Never touched |
| Its PDF is a candidate's current `stored_path` | PDF kept while the candidate exists; its metadata file deleted once the job finished |
| Finished job, no candidate uses the PDF (failed, duplicate, replaced by a newer resume, …) | PDF and metadata deleted 7 days after the job finished |
| In no job | Deleted after 1 day |
| Interrupted copy (`.part`) | Deleted after 1 hour |

Anything else in the folder is never touched. Running the command again is harmless. Details: [LLD §6.10](docs/LLD/06_Resume_Parsing_and_Skill_Extraction.md).

### Compute matches

After crawling jobs and uploading resumes, score every candidate against every job:

```bash
curl -X POST http://localhost:8000/background-jobs/match
```

To use other weights (an optional feature, implemented), send them with the request: four whole numbers from 0 to 100 that add up to exactly 100 (anything else is refused with 422; nothing is rescaled):

```bash
curl -X POST http://localhost:8000/background-jobs/match -H "Content-Type: application/json" \
  -d '{"weights": {"required": 60, "nice": 20, "experience": 10, "location": 10}}'
```

A run records its weights in `params.weights`. A run started without weights uses the active weights: the latest chosen ones, or `MATCH_WEIGHTS` (70, 15, 10, 5) if none were chosen. `GET /matching/weights` shows the default, active and current-results weights; in the UI, the Recompute dialog has the same form with "Reset to defaults".

The answer is `202 Accepted` with the `match` job; follow it like a crawl (one progress item per candidate). When it completes, it has replaced all stored matches at once; until then, and if it is cancelled or fails, the previous matches stay as they were. Then:

| Request | Shows |
|---|---|
| `GET /candidates/{id}/matches?limit=10` | A candidate's top jobs (default and maximum 10) |
| `GET /jobs/{id}/matches?limit=10` | A job's top candidates |

Each item has its `rank`, the `score` (2 decimals), `matched_skills` and `missing_skills` (each `{skill, level}`), the `breakdown` of the four components, `text_similarity` and the `explanation`. `computed_at` says when the matches were computed. After a crawl that saved new jobs, or changed what matching reads from a job, a match run is queued automatically (below); after uploading resumes, run the job yourself.

**Automatic re-matching** (an optional feature, implemented). When a crawl ends `completed`, or `failed` after saving jobs, and it saved a new job or changed a job's skills, minimum experience, location, remote flag or description, the worker queues a match run with the active weights. Its `params.after_crawl` names the crawl, and the crawl's log says what happened. A job fetched again unchanged does not count. Nothing is queued after a cancelled crawl, when there are no candidates yet, or when a match run is already queued (it includes the new jobs). Set `AUTO_REMATCH=false` to recompute only by hand.

### Search, details and exports

```bash
curl "http://localhost:8000/jobs?q=python&skill=js&location=bangalore&max_required_years=3&sort=title&page=1&page_size=20"
curl "http://localhost:8000/jobs/{job_id}"
curl "http://localhost:8000/candidates?skill=reactjs&city=pune&sort=years_experience"
curl "http://localhost:8000/candidates/{candidate_id}"
curl "http://localhost:8000/skills"
curl -OJ "http://localhost:8000/exports/jobs?format=csv&skill=python"       # saves jobs_<UTC time>.csv
curl -OJ "http://localhost:8000/exports/candidates?format=json"
curl -OJ "http://localhost:8000/exports/matches?format=csv&top=10"          # the match table (samples/)
```

| Endpoint | Filters (combined with AND) | Sort (`sort`, `order`) |
|---|---|---|
| `GET /jobs` | `q` (title or company), `skill`, `location`, `job_type`, `max_required_years`, `listing` (`real` or `demo`), `industry`, `source` | `posted_date` (default, newest first) or `title` |
| `GET /candidates` | `q` (name or current title), `skill`, `city` | `name` (default, A to Z) or `years_experience` |

- **Filters.**
  - Text filters are case-insensitive substrings.
  - `skill` accepts aliases ("js" finds JavaScript, "reactjs" finds React) and matches a job's required or nice-to-have skills. A term that isn't a known skill finds nothing.
  - A known city matches all its spellings ("bangalore" finds "Bengaluru").
  - `max_required_years=3` returns jobs asking for at most 3 years, plus jobs with no minimum.
  - `listing=real` keeps jobs from real company sources, `listing=demo` the invented jobs of the demo sites; every job also carries `listing` and `industry`, and `GET /jobs/{id}` adds `industry_reasons`, the evidence for the industry.
  - A blank filter counts as not set.
- **Sorting and paging.**
  - Missing values sort last, and equal values are ordered by ID.
  - `page` starts at 1. `page_size` defaults to 20 and is at most 100.
  - Lists answer `{items, total, page, page_size}`, and a page after the last has no items.
- **Errors.** An unknown query parameter or an invalid value gives 422. An unknown ID gives 404.
- **Details.** `GET /jobs/{id}` returns every field of the job with both skill lists. `GET /candidates/{id}` returns the candidate's fields and parse warnings. Their matches come from the `/matches` routes above.
- **Privacy.** Candidate responses carry the candidate fields of the brief (name, email, phone, city, title, skills, years, education, summary, source file name, OCR flag). They never include the stored file path or the resume text.
- **Exports.**
  - Each export takes the same filters and sort as its list, without paging; any other parameter (including `page`) gives 422:

    | Export | Required | Filters | `sort` | `order` | Other |
    |---|---|---|---|---|---|
    | `/exports/jobs` | `format` = `csv` or `json` | `q`, `skill`, `location`, `job_type`, `max_required_years`, `listing`, `industry`, `source` | `posted_date` (default) or `title` | `asc` or `desc`; default `desc` for `posted_date`, `asc` for `title` | |
    | `/exports/candidates` | `format` | `q`, `skill`, `city` | `name` (default) or `years_experience` | `asc` or `desc`; default `asc` for `name`, `desc` for `years_experience` | |
    | `/exports/matches` | `format` | `q`, `skill`, `city` (choose the candidates) | `name` (default) or `years_experience` (order of the candidates) | as `/exports/candidates` | `top` = 1–10, default 10 (jobs per candidate) |

  - The match table reads the stored matches and ranks each candidate's jobs exactly like `/candidates/{id}/matches`. Its rows follow the candidates in the chosen order, then the rank. For example, `/exports/matches?format=csv&top=3&sort=years_experience&order=desc` lists the most experienced candidate's top 3 first.
  - Files are streamed and named `<entity>_<UTC time>.<csv|json>`.
  - In CSV, lists are joined with `; ` and dates are ISO 8601. A text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'`, so a spreadsheet does not run it as a formula.
  - An empty export is the CSV header only, or `[]`.

### Services

| Service | Role | Host port |
|---|---|---|
| `frontend` | Serves the built React app | 5173 |
| `api` | FastAPI on Uvicorn; applies database migrations, then serves | 8000 |
| `worker` | Celery worker for crawl, resume and match tasks, 2 processes; includes headless Chromium, PyMuPDF, pdfplumber, Tesseract OCR and scikit-learn | none |
| `db` | PostgreSQL 17 (volume `pgdata`) | none |
| `redis` | Redis, the Celery message broker | none |
| `mock-site` | Optional demo job site (`mock-site/`): static pages, one JavaScript page, its own robots.txt; `http://mock-site:8080` inside Compose | none |

Start-up order: `db` and `redis` become healthy, then `api` starts, then `worker` (once the API is healthy, so the schema exists). Every service has a health check: the API calls `/health` (PostgreSQL and Redis), the worker answers a Celery ping through Redis, and the frontend, database, Redis and mock site answer their own probes, so `docker compose ps` shows each as healthy. When the worker starts, it fails stale background jobs and syncs the `skills` table from `backend/app/skills/taxonomy.json`.

## Architecture and design decisions

```text
 Browser ── React UI (frontend) ──HTTP──► FastAPI (api) ──────────► PostgreSQL
                                             │  saves the job,        (jobs, candidates, skills, matches,
                                             │  then sends its ID      background jobs and their logs)
                                             ▼                              ▲
                                        Redis (broker) ──► Celery worker ───┘
                                                           crawl · resume · match
```

The API only validates, stores and reads. All slow work (crawling, PDF parsing and OCR, scoring every pair) runs in the worker, and every result, status, progress count and log line is written to PostgreSQL, where the UI reads it by polling. The full reasoning, with the alternatives that were rejected, is in [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md) (28 ADRs). The main decisions:

| Decision | Why | ADR |
|---|---|---|
| One backend codebase (modular monolith), run as two processes: the FastAPI server and Celery workers | One developer can explain all of it; no network hops between services; heavy work never blocks a request | 001, 023 |
| PostgreSQL is the source of truth for background jobs; a Redis message carries only the job's ID | Status, progress and logs survive a Redis restart, and no personal data passes through the broker | 003, 004 |
| Conditional state changes, cooperative cancellation, heartbeats; one bad page or file never fails the whole job | A finished job is never overwritten, a cancelled job stops at the next page or file, a lost worker is detected, and partial success shows its succeeded and failed counts | 005, 006, 026 |
| The UI polls for progress | Simpler than WebSockets, and enough for jobs that take seconds to minutes | 007 |
| Polite breadth-first crawler with one extractor plug-in per site; Playwright only when the static HTML lacks the jobs | Adding a source is one file; most pages need no browser; robots.txt, rate limits and the SSRF guard apply to every source | 008–012 |
| PyMuPDF for text and layout, pdfplumber for tables and garbled pages, Tesseract for scans; a resume that cannot be read is flagged | Each library does what it is best at; nothing is guessed | 013, 014 |
| Own skills taxonomy with aliases and rules, used for jobs and resumes alike | Deterministic and testable; "ReactJS" and "React" are the same skill on both sides | 015 |
| The brief's formula unchanged, computed with exact fractions, with written edge-case rules; TF-IDF only to order exactly equal scores | Every score can be checked by hand and explained in one sentence | 016–018 |
| All pairs precomputed by a `match` job and replaced in one transaction | Top-10 pages and exports are single indexed reads; readers never see half a run | 019 |
| De-duplication: jobs by their apply URL, candidates by file hash and email | A listing card and its detail page become one job; a re-uploaded resume is skipped | 020 |
| Real or demo is derived from the job's source, never stored as a separate flag | An invented job can never be shown as a real opening | 028 |
| Routes without a version prefix (`/candidates/{id}/matches`, not `/api/v1/…`) | The paths match the brief exactly | 027 |
| No user accounts or authentication in the application | Out of scope for this assignment. Run FITSCAN on a trusted machine, or publicly behind the production proxy, which asks for a password over HTTPS ([Deploy publicly](#deploy-publicly)) | none |

## How crawling works

A crawl is a background job: the API saves it as `queued`, commits, and sends Redis a message that holds only the job ID. The worker claims it with a conditional update (`queued` → `running`), so a job cancelled meanwhile is never run. Every state change is conditional, so a final state (`completed`, `failed`, `cancelled`) is never overwritten.

- **Breadth-first**, from the seed, level by level, up to `max_depth` and `max_pages`. URLs are normalized (case, default ports, fragments, tracking parameters, sorted query), and each is fetched once.
- **Polite.** It stays on the allowed domains (default: the seed's host), follows robots.txt, waits `CRAWLER_DEFAULT_DELAY_SECONDS` between requests to a host (longer if robots.txt asks), and slows down after HTTP 429.
- **Retries** timeouts, connection errors, 429 (honouring `Retry-After`) and 5xx with exponential backoff and jitter. Other 4xx responses and non-HTML content are not retried.
- **Safe.** Every host, redirect hop and browser sub-request is checked against the allow-list and the SSRF guard. Private, loopback, link-local and reserved addresses are refused, except hosts in `CRAWLER_PRIVATE_HOST_ALLOWLIST`.
- **Fault-tolerant.** Each page has its own error boundary; a failed page is logged and counted, and the crawl continues.
- **Extractors** are plug-ins: one file per site in `backend/app/extractors/`, found automatically. A page is fetched with httpx; Playwright renders it only if the extractor says the static HTML lacks the jobs.
- **Each job** is normalized (ISO dates, salary numbers, job type, remote, years of experience), its skills are extracted and split into required and nice-to-have, it is validated with Pydantic, and it is upserted by `dedup_key` (the apply URL), so a listing card and its detail page become one job.
- **Progress** after every page: pages processed / `max_pages`, succeeded and failed counts, and a heartbeat. Pages discovered, jobs extracted and jobs saved are in the log lines.
- **Page limit.** A crawl that reaches `max_pages` while discovered pages are still queued ends `completed` and logs a warning: "Stopped at the page limit (max_pages N): M discovered pages were not visited". Jobs seen only on a listing page have no description, so no skills, until a later crawl reaches their own page, which then completes them in place. Fake Python Jobs needs `max_pages` 101 or more (its listing and 100 job pages); the New crawl dialog's default is 50.
- **Stale jobs.** A running job without a heartbeat for `JOB_HEARTBEAT_TIMEOUT_SECONDS`, or a queued job not picked up within `JOB_QUEUED_TIMEOUT_SECONDS` while no job writes heartbeats, is marked `failed` (when the worker starts and whenever jobs are listed). Lost tasks are not re-sent.

Supported sources: company career pages with schema.org `JobPosting` JSON-LD (`generic`), Greenhouse boards (`greenhouse`) and Lever boards (`lever`), read through their public JSON APIs; and the demo sites [Fake Python Jobs](https://realpython.github.io/fake-jobs/) (`fake_python_jobs`) and the mock site (`mock_static`, `mock_dynamic`), whose jobs are always labelled demo. Each job is classified into an industry from its title, skills and description (it never changes a match score). To add a source, add `backend/app/extractors/<site>.py` with a `BaseExtractor` subclass (see [`DATA_SOURCES.md`](DATA_SOURCES.md)).

## How resume parsing works

An upload is a background job, like a crawl (LLD Part 6).

- **Total size first.** A middleware counts the bytes of an upload request while it streams in. Over `MAX_UPLOAD_REQUEST_MB` (default 50), the request is stopped at once with 422: a declared `Content-Length` is refused before anything is read, and a chunked request is cut off at the limit, so at most that much is ever spooled. The connection is then closed. curl sends nothing at all (it waits for `100 Continue`).
- **API checks, file by file.** The size is counted while the file is copied in chunks, so an oversized file is never read into memory as a whole. The first bytes must be `%PDF-`; the extension and content type are checked but never trusted on their own. A rejected file does not stop the others.
- **Storage.** An accepted file is saved as `<upload_id>.pdf`, where `upload_id` is a random UUID, on the `uploads` volume, with a small `<upload_id>.json` that holds its original name for the worker. The job's parameters list only upload IDs and storage names, and `GET /background-jobs/{id}` shows only each file's short upload reference and size, never a file name or storage name; after parsing, the original name is kept only as `candidates.source_file`, never as a path. No endpoint serves the uploads volume. The API image has no PDF or OCR libraries; it only checks and stores.
- **Worker, one file at a time.** It computes the file's SHA-256; a file already saved is logged as "duplicate file, skipped". PyMuPDF opens the file: a corrupt, password-protected or too-long (`PDF_MAX_PAGES`) file fails with a clear message, and the next file is processed.
- **Text.** PyMuPDF returns text blocks with coordinates and font sizes. A two-column page (two groups of blocks side by side, with an empty gutter between them) is read left column first, then right column; anything else top to bottom, left to right. pdfplumber extracts tables, and replaces PyMuPDF's text on a page that looks garbled.
- **OCR.** A page with almost no text (`OCR_MIN_TEXT_CHARS`) but an image is rendered at 300 DPI and read by Tesseract (`OCR_LANGUAGE`, `OCR_TIMEOUT_SECONDS` per page). If OCR is disabled, missing, times out or finds nothing, the page is flagged; a resume without usable text is flagged and no candidate is created. `parsed_with_ocr` is true when any page's text came from OCR.
- **Fields**, with simple rules: name (largest font near the top of page 1; OCR text: first non-contact line), email, phone (digits with an optional `+`), city (from `backend/app/locations/cities.json`, shared with job locations so that "Bangalore" and "Bengaluru" are the same city), current title, years of experience (an explicit "6+ years of experience", otherwise the date ranges of the Experience section merged so overlaps count once, with "Present" meaning the parse date), education entries, summary, and skills (the same taxonomy and rules as jobs; the Skills section and table cells count as skill context).
- **Validation.** `CandidateRecord` (Pydantic) checks every field. An invalid optional field becomes null with a note in `parse_warnings` ("invalid email removed"), so the candidate is still saved.
- **Saving.** A new resume with the same email (ignoring case) as an existing candidate replaces that candidate's parsed fields and skills; otherwise a new candidate is created.
- **Privacy.** Log lines identify files by the first 8 characters of their upload ID and give page numbers, but never contain file names, names, contact details or resume text. Neither do the job's parameters, Redis messages or `GET /background-jobs/{id}`. Error messages and tracebacks in the server log are reduced to the exception type and code location, and SQL parameters are never shown.

## How matching works

A match run is a background job (LLD Part 7). It scores **every candidate against every job**, one pair at a time, and stores every pair in `matches`.

```text
score = 70 × R + 15 × N + 10 × E + 5 × L          (default weights: MATCH_WEIGHTS, adding up to 100)
```

| Component | Value between 0 and 1 |
|---|---|
| **R**, required skills | required skills the candidate has ÷ the job's required skills |
| **N**, nice-to-have skills | nice-to-have skills the candidate has ÷ the job's nice-to-have skills |
| **E**, experience | `min(1, candidate's years ÷ job's minimum)`: linear below the minimum |
| **L**, location | 1 if the job is remote or in the candidate's city, otherwise 0 |

The score is between 0 and 100. For example, a candidate with 3 of a job's 4 required skills, 1 of its 2 nice-to-have skills, 2 years against a 3-year minimum, in the job's city, scores 70 × 3/4 + 15 × 1/2 + 10 × 2/3 + 5 × 1 = 71.67. A match run can use other weights: four whole numbers that add up to 100 (see [Compute matches](#compute-matches)). The run records the weights it used; the hand check below used the defaults.

Skills are compared by their canonical names from the taxonomy, so "ReactJS" on a resume matches "React" in a job; a candidate's other skills neither add nor remove points. Cities go through the same normalizer as resume parsing, so "Bangalore, Karnataka" and "Bengaluru" are the same city; a city that is not in `cities.json` is compared by the text before the first comma. "Hybrid" jobs count as city-based.

**Edge cases** (ADR-017):

| Case | Rule |
|---|---|
| The job has required skills but no nice-to-have list | N = 1 (the candidate misses none of them). This gives 15 points even to a candidate who has none of the required skills; see the hand check below. |
| The job has nice-to-have skills but no required ones | R = 0, noted in the explanation |
| **The job has no skills at all** (extraction found none) | R = 0 **and** N = 0, so it scores at most 15 (experience and location). With N = 1 such jobs got 25–30 free points and outranked real partial matches. They are still scored and stored. |
| The job has no minimum experience | E = 1 |
| The job has a minimum but the resume shows no experience | E = 0 ("experience not found in resume") |
| The candidate's or the job's city is unknown and the job is not remote | L = 0 |

**Exact scores.** The score is computed with exact fractions and stored unrounded (`DOUBLE PRECISION`): two different scores never become equal, and two equal scores are stored identically. It is rounded to 2 decimals only for display, after ranking.

**Ranking.** Top 10 by score; exactly equal scores are ordered by the TF-IDF cosine similarity of the job description and the resume text (scikit-learn, worker only), then by the required-skill ratio, then by ID. Text similarity is never part of the score.

**Explanation.** Every match stores its matched and missing skills (each with its level), a breakdown of the four components (counts, ratios, points and the rule that applied), and a sentence generated from that breakdown:

> Score 71.67/100. Has 3 of 4 required skills (52.50 pts; missing Docker). Has 1 of 2 nice-to-have skills (7.50 pts; missing Kubernetes). 2 years of experience against a 3-year minimum (6.67 pts). Same city, Pune (5.00 pts).

**The run.** It loads all jobs and candidates, fits TF-IDF once, then scores one candidate (against all jobs) per progress step; cancellation is checked after each candidate. Nothing is written until every candidate is scored. Then, in one transaction, all old matches are deleted and the new ones inserted with one `computed_at`, so readers see either the complete old result or the complete new one. A cancelled or failed run leaves the previous matches unchanged. Log lines name candidates by the first 8 characters of their ID only.

## Matching hand check (5 candidates)

Done on 22 November 2026 on the stored results of the latest match run in the local development database (`computed_at` 13:50:44 UTC, default weights 70 / 15 / 10 / 5). Nothing was recomputed for this check. That run scored 128 jobs: the 108 demo jobs (100 from Fake Python Jobs, 8 from the mock site) and 20 real postings (10 from Code for America's Greenhouse board, 10 from Spotify's Lever board). 37 of the 128 jobs have extracted skills (18 demo, 19 real).

The [live demo](#deploy-publicly) holds a smaller synthetic set: the 108 demo jobs, without the 20 real postings, and the 4 candidates that `tests/resume_pdfs.py` generates, in which Kiran Rao's scanned resume is a copy of Asha Verma's. Nikhil Joshi and this check's Kiran Rao (a platform engineer in Hyderabad) are not on it, so some of its rankings differ from this table.

The 5 candidates were parsed from synthetic resumes made with `tests/resume_pdfs.py`; the people are invented, and Kiran Rao's resume is a scanned image read by OCR. The database also holds other uploaded resumes, which are not synthetic; they are left out of this README and of [`samples/`](samples/).

For each candidate, the top 3 jobs, in the order of `GET /candidates/{id}/matches`, were recalculated by hand from the database rows (the job's required and nice-to-have skills, its minimum years and location; the candidate's skills, years and city) and compared with the stored score, the score shown (2 decimals) and the explanation. R = required skills matched / required, N = nice-to-have matched / nice-to-have, and "no list" means N = 1 because the job lists no nice-to-have skills.

| Candidate (city, years) | Rank: job, company (location, listing) | Matched / missing skills | Hand calculation: R + N + E + L | Stored / shown |
|---|---|---|---|---|
| Asha Verma, Senior Backend Engineer (Pune, 6) | 1: Go Backend Engineer, Streamline (remote, demo) | Go, PostgreSQL, REST, Kubernetes / Kafka | 70·3/4 + 15·1/1 + 10 (6 ≥ 5) + 5 (remote) = 82.5 | 82.5 / 82.50 |
| | 2: Backend Python Developer, Acme Analytics (Pune, demo) | FastAPI, PostgreSQL, Python, Docker, Kubernetes, Redis / Django, Pytest | 70·3/5 + 15·3/3 + 10 (6 ≥ 3) + 5 (same city) = 72 | 72 / 72.00 |
| | 3: Staff Data Engineer, Code for America (remote in the U.S., real) | PostgreSQL, Python / 6 others, including Lead Generation and Warehouse Management | 70·2/8 + 15 (no list) + 10·6/7 + 5 (remote) = 645/14 | 46.07142857142857 / 46.07 |
| Kiran Rao, Platform Engineer (Hyderabad, 9.5; OCR) | 1: Go Backend Engineer, Streamline (remote, demo) | Go, PostgreSQL, REST, Kubernetes / Kafka | 70·3/4 + 15·1/1 + 10 (9.5 ≥ 5) + 5 = 82.5 | 82.5 / 82.50 |
| | 2: DevOps Engineer, CloudNest (Hyderabad, demo) | Docker, Kubernetes, Terraform / AWS, Linux, Ansible | 70·3/5 + 15·0/1 + 10 (9.5 ≥ 4) + 5 (same city) = 57 | 57 / 57.00 |
| | 3: Backend Python Developer, Acme Analytics (Pune, demo) | PostgreSQL, Python, Docker, Kubernetes, Redis / Django, FastAPI, Pytest | 70·2/5 + 15·3/3 + 10 + 0 (other city) = 53 | 53 / 53.00 |
| Meera Iyer, Frontend Developer (Chennai, 4.3) | 1: Full Stack Developer, Orbit Commerce (remote, demo) | Node.js, React, AWS / JavaScript, MongoDB, GraphQL | 70·2/4 + 15·1/2 + 10 (4.3 ≥ 3) + 5 = 57.5 | 57.5 / 57.50 |
| | 2: Staff Solutions Engineer, Code for America (remote in the U.S., real) | C#, Python / Java, Machine Learning, NLP, Procurement, Ruby | 70·2/7 + 15 (no list) + 10·4.3/7 + 5 = 323/7 | 46.142857142857146 / 46.14 |
| | 3: Frontend Engineer (React), Brightside Labs (Bengaluru, demo) | React, TypeScript / CSS, Git, Figma, Next.js | 70·2/4 + 15·0/2 + 10 (4.3 ≥ 2) + 0 = 45 | 45 / 45.00 |
| Nikhil Joshi, QA Automation Engineer (Chennai, 3.5) | 1: QA Automation Engineer, Testwise (Chennai, hybrid, demo) | Pytest, Python, Selenium, Jenkins / none | 70·3/3 + 15·1/1 + 10 (3.5 ≥ 2) + 5 (hybrid counts as city-based; same city) = 100 | 100 / 100.00 |
| | 2: Software Developer (Python), Moreno-Rodriguez (Martinezburgh, AE, demo) | Django, Flask, HTML, Python / none | 70·4/4 + 15 (no list) + 10 (no minimum) + 0 = 95 | 95 / 95.00 |
| | 3: Back-End Web Developer (Python, Django), Stewart-Alexander (South Kimberly, AA, demo) | CSS, Flask, HTML / Java | 70·3/4 + 15 (no list) + 10 + 0 = 77.5 | 77.5 / 77.50 |
| Rahul Mehta, Data Analyst (Bengaluru, 8.4) | 1: Data Analyst, Northwind Retail (remote, demo) | Excel, Power BI, SQL, Python / Data Analysis, Tableau | 70·3/4 + 15·1/2 + 10 (8.4 ≥ 1) + 5 = 75 | 75 / 75.00 |
| | 2: Staff Data Engineer, Code for America (remote in the U.S., real) | Power BI, Python, R, SQL / Lead Generation, PostgreSQL, Tableau, Warehouse Management | 70·4/8 + 15 (no list) + 10 (8.4 ≥ 7) + 5 = 65 | 65 / 65.00 |
| | 3: Machine Learning Intern, Lumen AI (Pune, demo) | Pandas, Python / Machine Learning, PyTorch | 70·2/3 + 15·0/1 + 10 (no minimum) + 0 = 170/3 | 56.666666666666664 / 56.67 |

**Result:** all 15 hand calculations equal the stored scores (the stored value is the exact fraction as a double), the shown scores are those values rounded to 2 decimals, and every explanation states the same points. No discrepancy was found.

**Do the top 3 make sense?**

| Candidate | Verdict | Why |
|---|---|---|
| Asha Verma | Yes for 1–2; 3 is weak | Ranks 1 and 2 are backend jobs built on her stack (Go, PostgreSQL, REST; FastAPI, PostgreSQL, Python), one remote and one in Pune. Rank 3 is a data-engineering role where she has 2 of 8 required skills. It ranks third with 46.07, far below 72: 17.5 points for skills, plus 15 because the posting lists no nice-to-have skills and 5 for remote, although it is remote within the U.S. |
| Kiran Rao | Yes | All three are infrastructure-heavy roles that fit a platform engineer: Go and Kubernetes (remote), DevOps with Docker, Kubernetes and Terraform in Hyderabad, then backend Python. |
| Meera Iyer | 1 and 3 yes; 2 questionable | Ranks 1 (full stack with React and Node.js) and 3 (React frontend) fit. Rank 2 is questionable for two reasons. Its location is "Remote (in the U.S.)", but FITSCAN counts any remote job as a location match, so a candidate in Chennai gets the 5 location points. And the posting lists no nice-to-have skills, so N = 1 gives 15 points, although she has only 2 of its 7 required skills (C# and Python, neither a frontend skill). Those 20 points put it 1.14 points above the React job, which lists two nice-to-haves she lacks (Figma, Next.js) and is in another city. |
| Nikhil Joshi | Rank 1 yes; 2–3 by skills only | Rank 1 is his exact role in his city (100). Ranks 2 and 3 are developer jobs, not QA, that match his web skills (Django, Flask, HTML and Python; CSS, Flask and HTML). The formula reads skills, not job titles. Both are Fake Python Jobs postings, whose skills come from generated filler text. |
| Rahul Mehta | 1 yes; 2 plausible; 3 questionable | Rank 1 is a data-analyst role. Rank 2 is a data-engineering role, not analysis, that uses his SQL, Python, R and Power BI. It is plausible on skills, but like Meera Iyer's rank 2 it is remote within the U.S. and still gets the 5 location points. Rank 3 is questionable: a Machine Learning Intern role for a candidate with 8.4 years of experience. The job sets no minimum, so E = 1 (10 points), and FITSCAN has no seniority or maximum-experience check, so an internship is never marked down. It ranks third on 2 of 3 required skills (Pandas, Python), although it is in another city (Pune) and he lacks its nice-to-have skill (PyTorch). |

**Other checks on the same run:**
- *Jobs without skills (O2).* 91 of the 128 jobs have no extracted skills, so they score at most 15. "Air broker" (West Colin, AP) scores 0 + 0 + 10 (no minimum) + 0 (other city) = **10** for each of the 5 candidates (stored 10; explanation "No required or nice-to-have skills could be identified for this job, so it gets no skill points"). No job without skills appears in any of the 5 candidates' top 10.
- *Exact ties.* Nikhil Joshi's ranks 4–6 (Senior Python Developer; Back-End Web Developer (Python, Django) in New Elizabethside; Python Programmer (Entry-Level)) all score exactly 215/3, stored as 71.66666666666667. They are ordered by text similarity: 0.1213, 0.0788, 0.0422.
- *Real and demo jobs together.* Real postings are in the top 10 of 4 of the 5 candidates (3 for Asha, Kiran and Meera, 4 for Rahul, none for Nikhil), scored by the same formula.

**Observations:**
- *A job with required skills but no nice-to-have list gives 15 points.* This is the N = 1 rule, **kept** (ADR-017, LLD §7.5): without it, a perfect candidate for such a job could score at most 85. None of the 20 real postings has nice-to-have skills that FITSCAN detected, and Fake Python Jobs pages never list any, so all of them get the 15 points. Against a demo job that lists nice-to-haves the candidate lacks, this can move a weaker skill match up by one place, as in Meera Iyer's rank 2. The explanation says why ("The job lists no nice-to-have skills (15.00 pts).").
- *Keyword skill extraction makes mistakes on real postings.* It matches taxonomy words and aliases without knowing the sense in which they are used. The Staff Data Engineer posting says "Lead generation and optimization of data architecture" (lead as a verb) and "data warehouses". These were read as the skills Lead Generation and Warehouse Management: two false required skills, which lower R for every candidate on that job.
- *"Remote" is not checked against the country.* The Code for America roles are remote within the U.S., but they get the 5 location points for candidates in India (Asha Verma's rank 3, Meera Iyer's and Rahul Mehta's rank 2).
- *Titles do not produce skills.* Rahul Mehta misses "Data Analysis" for the Data Analyst job, because his resume says "Data Analyst" only as his title.

## Known limitations

- **Skills.** Skills come from FITSCAN's own taxonomy (`backend/app/skills/taxonomy.json`) and keyword rules. A skill missing from the taxonomy is never seen, and a skill word used in another sense can become a false skill (see the hand check). The precision and recall in [Tests](#tests) were measured on a small hand-labelled set; real postings contain more errors.
- **Required or nice-to-have.** A skill counts as nice-to-have only under a heading such as "Nice to have" or "Preferred", or in a sentence with words such as "preferred" or "a plus"; every other skill counts as required. A posting with no nice-to-have skills gets N = 1 (15 points), as all real postings in the current data do.
- **What the score reads.** Only skills, years of experience and city. Job titles, seniority, domain and the rest of the text are ignored: TF-IDF only orders exactly equal scores, and embedding-based matching was deferred. Extra experience is never penalised, because E is capped at 1.
- **Location** is remote or the same normalised city, nothing in between: no distance, no country or time-zone check for remote jobs, and "Hybrid" counts as city-based. Cities missing from `backend/app/locations/cities.json` are compared by the text before the first comma.
- **Resume parsing** uses layout and text rules (name from the largest font, title and years from the Experience section). An unusual layout can give a wrong or missing field; the title fix in commit `a422e47` is one example. OCR is Tesseract with English (`OCR_LANGUAGE=eng`), and its quality depends on the scan.
- **Matches are precomputed.** After resumes are uploaded, someone has to start a match run; automatic re-matching runs only after a crawl. Each run rescores every pair, which is fine at this size (ADR-019 records the path for larger data).
- **Crawling.** An interrupted crawl cannot be resumed (deferred), and a lost task is not re-sent. A site needs its own extractor, a Greenhouse or Lever board, or schema.org `JobPosting` data. Company career pages are verified only with a saved test page: the one live attempt (Shopify careers) found no jobs. A crawl's allowed domain is a whole host, so a crawl seeded at a careers page can wander to other pages of that host. Lever postings do not name the company, and Greenhouse publishes no salaries ([`DATA_SOURCES.md`](DATA_SOURCES.md)).
- **Demo data.** Fake Python Jobs is generated practice data: 85 of its 100 postings are other professions with filler text, only 10 (the Python postings) name any skill, none marks a skill nice-to-have, and every location is an invented town ("Joybury, AE"). Those 90 jobs score at most 15 by design (no skills: R = 0, N = 0), so they cannot tell candidates apart. The mock site's 8 jobs (required and nice-to-have skills, minimum experience, Indian cities, remote and hybrid) are the meaningful demo of matching; real postings are the better test of matching quality.
- **Duplicates.** Two people who share an email address would be merged into one candidate (ADR-020).
- **Security and privacy.** There are no user accounts; FITSCAN is meant for a trusted machine or network. A public deployment is protected by one shared password at the proxy (HTTP Basic authentication over HTTPS), not by per-user logins. Uploaded resumes stay on the `uploads` volume until the retention command is run.

## Time spent

**About 60 hours**, from 11 to 22 November 2026, at about 5 hours a day (the author's estimate).

The git history starts on 18 November. The design documents in [`docs/`](docs/) (HLD, architecture decisions, LLD) were written before that and first committed with Phases 1–3. Commit dates are India Standard Time:

| Date (2026) | Work, by commit |
|---|---|
| 18 November | Phases 1–3: project setup, database, background jobs and the crawler (`af0c829`, `37253d6`) |
| 19 November | Phase 4: resume upload, PDF parsing and OCR (`d1eb2bb`); Phase 5: matching engine (`9d41403`); Phase 6: search, detail and export API (`bbe6bdb`) |
| 21 November | Phase 7: landing page (`221dccc`, `441225d`, `1c32d69`); Phase 7B: application UI (`ed764a2`) |
| 22 November | Phase 7C: adjustable weights, automatic re-matching and CI (`70be8ea`); Phase 7D: real jobs across industries (`1627f53`); Phase 8: integration and verification (`b724382`); resume title fix (`a422e47`); sample outputs and this README; the public deployment set-up (`e2c5fdd`) |
| 23–24 November | Public deployment and hardening (`334f637`, `2e854d9`); fixes from the production audits (`c94e0cc`, `8108ce2`); final documentation. The deployment work, from `e2c5fdd` on 22 November onwards, is outside the 60-hour estimate above. |

## Local development

Run PostgreSQL and Redis in Docker, and the code from your machine, for fast reloads. Requires Python 3.12 and Node.js 24.

**1. Configuration and services**

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db redis
```

`docker-compose.dev.yml` publishes PostgreSQL on `127.0.0.1:5433` and Redis on `127.0.0.1:6379`, which is where `DATABASE_URL` and `REDIS_URL` in `.env` point. Port 5433 avoids clashing with a PostgreSQL installed on the machine.

**2. Backend API** (from `backend/`)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev,worker]"    # worker = Playwright, PyMuPDF, pdfplumber, pytesseract, scikit-learn; then `playwright install chromium`
alembic upgrade head
uvicorn app.main:app --reload
```

**3. Worker** (second terminal, from `backend/` with the virtual environment active)

```bash
celery -A app.worker.celery_app worker --loglevel=INFO --pool=solo
```

`--pool=solo` is needed on Windows only. Check that the worker is up with `celery -A app.worker.celery_app inspect ping`. To OCR scanned resumes from the venv, install the Tesseract program as well; without it, scanned resumes are flagged (the worker image includes it).

**4. Frontend** (third terminal, from `frontend/`)

```bash
npm ci
npm run dev
```

The dev server runs on http://localhost:5173 and reads `VITE_*` variables from the root `.env`.

## Tests

```bash
cd backend && pytest            # unit tests, offline: no database, Redis or internet needed
cd frontend && npm run build    # TypeScript type check + production build
cd frontend && npm run check:sidebar   # the sidebar's link classes, full and collapsed (tablet rail)
```

The unit tests cover the crawler (BFS, normalization, robots.txt, rate limiting, retries, 429/5xx/4xx, redirects, SSRF), the extractors on saved pages in `tests/fixtures/html/`, skill extraction, job validation, and resume parsing: upload checks (signature, streamed size limit, names as data only), PDF opening (corrupt, encrypted, page limit), reading order of one- and two-column pages, tables, the garbled-text fallback, scanned-page detection and OCR failures, every candidate field (including overlapping employment dates against a fixed "today") and `CandidateRecord` validation, and matching: the worked example, every scoring edge case (including jobs without skills), experience and location rules (remote, hybrid, unknown and unlisted cities, Bangalore = Bengaluru), exact scores, display rounding, the explanation text against the breakdown, the TF-IDF tie-breaker, the ranking order and the four score-precision cases of LLD §9.7, and search and export: parameter validation (422 for every bad or unknown parameter), the SQL of each filter and sort, CSV cell safety, quoting and filenames, and JSON streaming. They never use the internet: pages come from `httpx.MockTransport`, DNS is faked, and resumes are synthetic PDFs generated by `tests/resume_pdfs.py` (invented people only; no real resume is used).

Skill extraction is measured on hand-labelled examples (LLD §6.9): job descriptions give precision 1.00 and recall 1.00; resumes give precision 1.00 and recall 0.95. The one known miss is "Swift" at the start of a sentence, which the ambiguous-word rule ignores outside a skill context.

**Database integration tests** run against a real PostgreSQL. They check:
- the migration: upgrade from an empty database, downgrade and upgrade again, models = database (`alembic check`), keys, constraints, cascades and full-precision scores;
- background jobs: the API, state rules, cancellation, progress, logs, stale-job checks and worker failures;
- saving crawled jobs and candidates (new, duplicate file, same email);
- the upload retention command against real jobs and candidates: dry run, `--delete` for every rule, and a second run that changes nothing;
- a full crawl through the API, with Celery running the real `crawl` task in-process against the mock site;
- a full resume upload through the API with the real `resume` task: accepted and rejected files, UUID storage, progress, logs, duplicates, same-email updates, cancellation between files, OCR, a broker outage, and a check that no log line contains names, contact details, file names or resume text;
- search and detail: every filter on its own and combined, aliases and city spellings, literal `%` and `_`, sorting with missing values last, page boundaries, the exact response fields, two queries per page and one per detail read, 404 and 422, no internal or private columns, and `/skills`;
- exports: headers and filenames, empty exports, the same rows and order as the search, CSV quoting of commas, quotes and line breaks, formula-injection protection (CSV only), streaming in small batches, the match table against the stored matches and `/candidates/{id}/matches` (rank, score, breakdown, explanation), `top` and the candidate filters, and a check that no search, detail or export request starts a match run or changes a match;
- a full match run through the API with the real `match` task: every pair stored with one `computed_at`, the edge cases in the database, reruns that replace every row, cancellation and failures that keep the previous matches, two runs saving at the same time, the heartbeat before the final write, no personal data in the logs, both top-10 routes (shape, limit, 404), the API order against the ranking rule on data with many ties, and the score-precision cases through PostgreSQL;
- real job sources: Greenhouse, Lever and career-page fixtures crawled through the API (fields, industries, real listings, original posting), no duplicates on re-crawl, real and demo jobs side by side with the new filters, the source columns in exports, one matching engine for both kinds, demo hosts refused for real-source extractors, and the industry migration on existing jobs;
- adjustable weights and automatic re-matching: custom weights give exact scores, the active weights (failed and cancelled runs never change them), change detection for every value matching reads, the crawl trigger rules (completed, failed, cancelled, no candidates, `AUTO_REMATCH=false`), no duplicate runs under concurrent requests, a broker failure that leaves the crawl unchanged, and an older run never overwriting newer results.

They are skipped unless `TEST_DATABASE_URL` is set. With the dev override running (step 1 of *Local development*):

```bash
docker compose exec db createdb -U app matching_test     # once
cd backend
TEST_DATABASE_URL=postgresql+psycopg://app:change-me@127.0.0.1:5433/matching_test pytest
```

On Windows PowerShell, set the variable first: `$env:TEST_DATABASE_URL = "postgresql+psycopg://…/matching_test"`. The tests drop and recreate the schema of that database, so it must be `matching_test`: the URL must name it and the server must confirm it before anything is dropped, otherwise the test run stops without changing anything. While tests run, `DATABASE_URL` is replaced by an offline placeholder unless it also names `matching_test`, so the application code under test cannot reach the development database.

**OCR with the real Tesseract, in the worker image.** Two tests in `tests/unit/test_ocr.py` need the Tesseract program and are skipped without it. The worker image has it, as well as the worker-only libraries (PyMuPDF, pdfplumber, scikit-learn). To run all unit tests there (from the repository root; `tests/` is mounted because the image does not contain it):

```bash
docker compose run --rm --no-deps -v ./backend/tests:/app/tests:ro worker \
  sh -c "pip install --user -q pytest==9.2.0 && python -m pytest -p no:cacheprovider tests/unit"
```

The container gets every variable of `.env` from Compose. The settings tests remove all of them first, so they check the built-in defaults wherever they run.

**Continuous integration.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and pull request to `main`. The backend job runs the whole suite (unit tests, the database integration tests against a throwaway PostgreSQL service whose only database is `matching_test`, and OCR with Tesseract) and fails if any test is skipped (1158 tests on 24 November 2026). The frontend job runs `npm ci`, `npm run build` and `npm run check:sidebar`. It needs no secrets.

## Configuration

All settings are environment variables, documented in [`.env.example`](.env.example) and read by `backend/app/config.py` (HLD §16.3).

- One `.env` in the repository root serves Docker Compose, the backend and Vite.
- Inside Docker, `docker-compose.yml` overrides `DATABASE_URL`, `REDIS_URL` and `UPLOAD_DIR` with container values (host names `db` and `redis`).
- `AUTO_REMATCH` (default `true`) queues a match run after a crawl that saved new or changed jobs (see "Compute matches").
- `API_DOCS_ENABLED` (default `true`) serves the API documentation at `/docs`, `/redoc` and `/openapi.json`; with `false` those paths do not exist. `VITE_API_DOCS_ENABLED` (default `true`, build time) shows the frontend's links to them. Production sets both to `false`.
- `VITE_API_BASE_URL` and `VITE_POLL_INTERVAL_MS` are compiled into the frontend at build time. After changing them, rebuild: `docker compose up --build frontend`.
- Host-side URLs use `127.0.0.1`, not `localhost`: on Windows, psycopg can stall trying IPv6 (`::1`) first.

## Deploy publicly

FITSCAN can run around the clock on one free **Oracle Cloud Always Free** Arm VM (Ubuntu 24.04, `VM.Standard.A1.Flex`, 2 OCPUs, 4 GB), with a free DuckDNS host name and a Let's Encrypt certificate. It's the only free option checked that runs every service (the Celery worker included) and keeps its data. Render, Vercel, Fly.io, Railway, Koyeb and Google's e2-micro were ruled out; [`deploy/README.md`](deploy/README.md) gives the reasons, the limits and every step. On the server, after cloning:

```bash
cp deploy/production.env.example .env      # then fill in the host name, the login's bcrypt hash and a database password
bash deploy/check-env.sh                    # refuses placeholders and unsafe values; prints key names only
```

Then build the images one at a time and start the stack, as in steps 3–6 of the guide (a 4 GB server also needs the swap
file and log limits set up there).

[`docker-compose.prod.yml`](docker-compose.prod.yml) changes only what production needs; plain `docker compose up` stays as it is:

- A Caddy proxy ([`deploy/caddy/`](deploy/caddy/)) is the only published service, on ports 80 and 443. It obtains the certificate, redirects HTTP to HTTPS, asks for a password for everything except `GET /api/health`, adds security headers, limits request rates and sizes, and marks API responses `no-store`. The frontend is at `/` and the API at `/api/`, so they share one origin.
- The API, the frontend, PostgreSQL, Redis and the worker are not published. The API runs with `API_DOCS_ENABLED=false`, and the frontend is built without docs links.
- The mock site runs only with `--profile demo`.
- The stack runs as its own Compose project, `fitscan-prod`, so its database volume is always new and separate from a local `fitscan` stack.

The server gets its own, empty database. Fill it with synthetic data only: the demo job sites and the generated resumes from `tests/resume_pdfs.py`. Never copy a local database, backup or upload there.

**The live deployment** (<https://fitscan-demo.duckdns.org>, since 23 November 2026) follows this guide. Its data is synthetic only: Fake Python Jobs (100 demo jobs) and the mock site (8 demo jobs), the generated resumes (3 invented people plus a scanned copy of one, read by OCR), and one match run over all pairs. A systemd timer backs up the database every day ([Backups and restore](deploy/README.md#backups-and-restore)).

**Cost:** $0 within the Always Free allowance (2 OCPUs and 12 GB in total, 200 GB of storage, 10 TB of outbound data a month). A Free Tier account that is never upgraded can't create paid resources; charges are possible only after upgrading to Pay As You Go. Sign-up needs a card for verification. Oracle may reclaim a VM that stays idle for a week, and it halved the Arm allowance in June 2026, so keep database backups.

## Security controls

- **No secrets in the repository.** `.env` is git-ignored; `.env.example` holds placeholders only. Containers run as non-root users.
- **Exposed ports.** Locally, only the API (8000) and the UI (5173) are published. PostgreSQL and Redis are reachable only inside Compose (the development override publishes them on `127.0.0.1` only). In production only the proxy is published (80 and 443).
- **API.** Every query and body is validated by Pydantic; unknown query parameters are a 422; one error envelope; bounded page sizes; queries use bound parameters (literal `%` and `_` in searches); CORS allows only `CORS_ORIGINS`.
- **Job details and logs.** `GET /background-jobs/{id}` and `/logs` show a sanitised copy (`app/services/redaction.py`); the stored rows are unchanged. URLs lose credentials, fragments and secret query values. Internal host names and IP addresses, file-system paths, stack traces, e-mail addresses, phone numbers and `password=`-style secrets are replaced. Upload and candidate IDs are shortened to 8 characters, and storage names are dropped. Counts, levels, public page URLs, retries, robots.txt results and failure summaries stay visible.
- **Crawler.** Allow-listed hosts only; private, loopback, link-local and reserved addresses refused on every redirect hop and browser request (DNS checked); robots.txt and `Crawl-delay` obeyed; per-host rate limit, bounded retries, 5 MB page limit; no logins or access controls are bypassed; demo-site jobs can never be stored as real.
- **Resumes.** Size limits per file and per request (checked while streaming), `%PDF-` signature check, page limit, OCR time limit, UUID storage names (never the user's file name), a read-only uploads volume for the worker, logs without names or contact details, and a retention command for old uploads.
- **Exports.** Streamed; CSV cells that could start a formula are neutralised.
- **Worker.** One bad item never stops a job; stale jobs are failed by heartbeat checks; a match run never overwrites newer results; manual and automatic match requests share one database lock.
- **Production.** `docker-compose.prod.yml` puts a Caddy proxy in front: HTTPS, a password for everything except the health check, no API docs, rate and size limits, `no-store` caching for API responses and security headers ([Deploy publicly](#deploy-publicly)). The API sends no `Server` header, and resume jobs log only counts of unknown skill terms, never the words.
- **Out of scope.** There are no user accounts in the application: run FITSCAN on a trusted machine or network, or behind the production proxy.

## Database migrations

Alembic reads `DATABASE_URL` through `app.config`. From `backend/`:

```bash
alembic revision --autogenerate -m "describe the change"   # after changing models in app/models/
alembic upgrade head                                       # apply migrations
```

The `api` container runs `alembic upgrade head` every time it starts; on an up-to-date database this does nothing.

The first migration, `alembic/versions/98acdef52211_initial_schema.py`, creates the eight tables with their keys, unique, check and partial indexes, and enables the PostgreSQL `pg_trgm` extension used by the trigram search indexes. `alembic downgrade base` removes all of it again. After changing a model, `alembic check` reports whether a new migration is needed.

The second migration, `5d2e8c41a7b9_job_industry.py`, adds `jobs.industry` (indexed, limited to the 13 industry codes, default `other`) and classifies the jobs that already exist; it writes only that column. The `api` container applies it on its next start; `alembic downgrade 98acdef52211` removes the column again.

When the industry rules change, bring stored jobs up to date without a crawl (dry run first; only `jobs.industry` is written):

```bash
docker compose exec api python -m app.services.reclassify            # list what would change
docker compose exec api python -m app.services.reclassify --apply    # write it
```

## Project structure

```text
├── docker-compose.yml        # all services
├── docker-compose.dev.yml    # development only: publishes db and redis on 127.0.0.1
├── docker-compose.prod.yml   # production override: Caddy proxy in front, nothing else published
├── deploy/                   # public deployment: guide, Caddy proxy (Dockerfile, Caddyfile), production .env template
├── .env.example              # documented configuration, no secrets
├── DATA_SOURCES.md           # where jobs and resumes come from, terms and robots.txt checks
├── AI_USAGE.md               # how AI tools were used
├── SUBMISSION.md             # submission summary for reviewers: live site, features, testing, how to review
├── samples/                  # sample outputs (synthetic data only): jobs, candidates, top-10 match table
├── .github/workflows/ci.yml  # CI: every backend test, the frontend build and the sidebar check
├── backend/
│   ├── Dockerfile            # targets: api, worker
│   ├── pyproject.toml        # dependencies and pytest settings
│   ├── alembic.ini, alembic/ # database migrations (versions/: the initial schema, then jobs.industry)
│   ├── app/
│   │   ├── main.py           # FastAPI app: routers, CORS, error handlers
│   │   ├── config.py         # settings from environment variables
│   │   ├── errors.py         # standard error envelope
│   │   ├── api/              # routers: health, background_jobs, jobs, candidates, skills, exports, matching, sources; upload_limit
│   │   ├── schemas/          # Pydantic request/response models, JobRecord, CandidateRecord
│   │   ├── db/               # engine, sessions, Base (constraint naming)
│   │   ├── models/           # SQLAlchemy models: the eight tables of LLD Part 3
│   │   ├── services/         # background-job control, stale-job checks, search, top-10 match queries, export, upload retention
│   │   ├── worker/           # Celery app, crawl, resume and match tasks, state/progress/log helpers
│   │   ├── crawler/          # BFS frontier, fetcher, robots, rate limiter, URLs, SSRF, browser, pipeline
│   │   ├── extractors/       # plug-ins: base, registry, generic, greenhouse, lever, fake_python_jobs, mock_static, mock_dynamic
│   │   ├── resumes/          # validation, text_extraction, ocr, fields, pipeline
│   │   ├── locations/        # cities.json and the city normalizer (candidates and job locations)
│   │   ├── skills/           # taxonomy.json, normalizer, extractor, sync
│   │   ├── industries/       # industries.json (rules) and the industry classifier
│   │   └── matching/         # scoring (exact), explanation, ranking, tfidf (tie-breaker), engine (the match run)
│   └── tests/                # unit/ (offline), integration/ (PostgreSQL), fixtures/html, resume_pdfs.py (synthetic PDFs)
├── mock-site/                # optional demo job site (static + JavaScript pages, robots.txt)
├── frontend/
│   ├── Dockerfile            # Node builds the app; `serve` serves the static files
│   ├── package.json, vite.config.ts, tsconfig*.json, components.json
│   └── src/
│       ├── api/client.ts     # typed API client
│       ├── App.tsx           # routes: / landing page, /app dashboard and the application pages
│       ├── components/ui/    # shadcn/ui components (badge, button, card, dialog, input, label, progress, select, sheet, skeleton, table, toast, tooltip)
│       ├── components/sections/, components/landing/  # landing page sections and their parts
│       ├── lib/utils.ts      # shadcn/ui helper
│       ├── pages/LandingPage.tsx # marketing landing page (/), sample data only
│       ├── pages/DashboardPage.tsx, …  # application pages: /app dashboard, background jobs, jobs and candidates (each with a detail page), matching, skills, exports
│       ├── hooks/  types/
│       └── main.tsx
└── docs/                     # HLD, LLD, ADRs, diagrams, demo video script
```

The full planned layout is in [LLD Part 2](docs/LLD/02_Project_Structure.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| `env file .env not found` | Run `cp .env.example .env` first. |
| Build stops with `additional privileges requested: pass "--allow=fs.read=…"` (Windows) | The terminal's folder path differs in letter case from the real one (e.g. `c:\users\…` instead of `C:\Users\…`). Open the project folder again with its exact case and rerun. |
| `ports are not available` for 5173 or 8000 | Another program uses the port; stop it, or change the left-hand port in `docker-compose.yml`. |
| `GET /health` returns 503 | The response's `details` say whether `database` or `redis` is down. Check `docker compose ps`. |
| The UI shows the old API address | `VITE_*` values are build-time: `docker compose up --build frontend`. |
| The Celery worker exits at once on Windows | Add `--pool=solo`. |
| A crawl seed gets 422 "private or reserved address" | The SSRF guard refuses internal hosts. Only hosts in `CRAWLER_PRIVATE_HOST_ALLOWLIST` are exempt: `mock-site` in `.env.example`, none by default or in production. |
| A crawl of a JavaScript page fails with a browser error when running the worker from the venv | Run `playwright install chromium` once (the worker image already contains Chromium). |
| An upload returns 422 "the upload is larger than 50 MB in total" | All files of one request together exceed `MAX_UPLOAD_REQUEST_MB`. Send them in several requests. (Through Docker Desktop's port forwarding on Windows, a client that does not wait for `100 Continue` may only see the answer after it stops sending; curl is answered at once.) |
| An upload returns 422 `NO_VALID_FILES` | Every file was rejected; `details.rejected_files` gives each reason (`NOT_A_PDF`: the file does not start with `%PDF-` or is declared as another type; `FILE_TOO_LARGE`: over `MAX_UPLOAD_MB`). |
| A scanned resume is flagged "OCR produced no text (Tesseract is not installed)" | The worker runs outside Docker without Tesseract. Install it, or use the worker container. |
| A resume fails with "the file has N pages; at most 20 are allowed" | Raise `PDF_MAX_PAGES` in `.env` and restart the worker. |
| `GET /candidates/{id}/matches` returns `"items": []` and `"computed_at": null` | No match run has included this candidate yet (for example it was uploaded after the last run). Run `POST /background-jobs/match`. |
| A match job fails with "No candidates to match" or "No jobs to match" | Upload resumes or run a crawl first; the previous matches are unchanged. |
| A search or export returns 422 "Extra inputs are not permitted" for `query.<name>` | That parameter is not a filter of this endpoint (for example `company` on `/jobs`: use `q`, which searches titles and companies; `location` is `city` on `/candidates`; exports take no `page`). |
| `GET /jobs?skill=…` returns nothing although the word is in job texts | `skill` only matches skills of the taxonomy (`GET /skills`), by name or alias. Use `q` to search titles and companies. |
