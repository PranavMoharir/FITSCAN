# FITSCAN: Job–Candidate Matching Platform

A platform that collects job openings by crawling, reads candidate resumes from PDFs, and matches each candidate to the jobs that fit best (and each job to its best candidates). Crawling, parsing and matching run as background jobs; users watch progress, browse results and export CSV or JSON.

The design is in [`docs/`](docs/): the [detailed HLD](docs/HLD_Job_Candidate_Matching_Platform_Full.md), the [LLD](docs/LLD/README.md) and the [architecture decisions](docs/ARCHITECTURE_DECISIONS.md).

## Status

**Phases 1–4 done:** project setup, database, background jobs with the job crawler, and resume upload with PDF parsing and OCR. Crawls and resume parsing run in the Celery worker; their status, progress, logs, jobs and candidates are stored in PostgreSQL.

| Works now | Not built yet (later phases) |
|---|---|
| `docker compose up` starts the API, worker, PostgreSQL, Redis, UI and the mock job site | Matching engine and match endpoints |
| The eight tables of [LLD Part 3](docs/LLD/03_Database_Design.md) (SQLAlchemy models + Alembic migration) | Search and export endpoints, `GET /skills`, `GET /candidates` |
| Background jobs: create a crawl or a resume job, list, detail, logs, cancel; heartbeats and stale-job checks | UI pages (background jobs, jobs, candidates, upload form, detail pages) |
| Polite BFS crawler: robots.txt, rate limit, retries, SSRF guard, Playwright only when needed | `samples/`, `DATA_SOURCES.md`, `AI_USAGE.md` |
| Extractors: Fake Python Jobs, the mock site (static and JavaScript), generic JSON-LD | |
| Job validation, de-duplication (upsert by `dedup_key`), skills taxonomy and job skills | |
| Resume upload: size and `%PDF-` checks per file, UUID storage, one background job per upload | |
| PDF parsing: one- and two-column layouts, tables, garbled text, OCR of scanned pages (Tesseract) | |
| Candidate fields, skills, validation, de-duplication (same file skipped, same email updated) | |
| `GET /health`, OpenAPI docs at `/docs`, one error envelope for every error | |

The sections the brief asks for (how matching works, the 5-candidate hand check, known limitations, time spent) are added as those features are built.

## Quick start (Docker)

Requires Docker Desktop (or Docker Engine with Compose v2).

```bash
cp .env.example .env
docker compose up --build
```

| URL | What it is |
|---|---|
| http://localhost:5173 | Web UI (landing page with system status) |
| http://localhost:8000/docs | Interactive API documentation |
| http://localhost:8000/health | Health check: `{"status": "ok", "database": "ok", "redis": "ok"}` |

`.env.example` works as it is for local use. Change `POSTGRES_PASSWORD` (and the same password in `DATABASE_URL`) if the machine is shared.

Stop with `Ctrl+C`, or `docker compose down`. Data is kept in Docker volumes; `docker compose down -v` deletes it. The first build takes several minutes, because the worker image downloads headless Chromium.

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

A real site works the same way, for example `"seed_url": "https://realpython.github.io/fake-jobs/"`. The crawled jobs are in the `jobs` table, and their skills in `job_skills`.

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

### Services

| Service | Role | Host port |
|---|---|---|
| `frontend` | Serves the built React app | 5173 |
| `api` | FastAPI on Uvicorn; applies database migrations, then serves | 8000 |
| `worker` | Celery worker for crawl and resume tasks (match later), 2 processes; includes headless Chromium, PyMuPDF, pdfplumber and Tesseract OCR | none |
| `db` | PostgreSQL 17 (volume `pgdata`) | none |
| `redis` | Redis, the Celery message broker | none |
| `mock-site` | Optional demo job site (`mock-site/`): static pages, one JavaScript page, its own robots.txt; `http://mock-site:8080` inside Compose | none |

Start-up order: `db` and `redis` become healthy, then `api` starts, then `worker` (once the API is healthy, so the schema exists). When the worker starts, it fails stale background jobs and syncs the `skills` table from `backend/app/skills/taxonomy.json`.

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
- **Stale jobs.** A running job without a heartbeat for `JOB_HEARTBEAT_TIMEOUT_SECONDS`, or a queued job not picked up within `JOB_QUEUED_TIMEOUT_SECONDS` while no job writes heartbeats, is marked `failed` (when the worker starts and whenever jobs are listed). Lost tasks are not re-sent.

Supported sites: [Fake Python Jobs](https://realpython.github.io/fake-jobs/) (`fake_python_jobs`), the mock site (`mock_static`, `mock_dynamic`) and any page with schema.org `JobPosting` JSON-LD (`generic`). To add a site, add `backend/app/extractors/<site>.py` with a `BaseExtractor` subclass.

## How resume parsing works

An upload is a background job, like a crawl (LLD Part 6).

- **Total size first.** A middleware counts the bytes of an upload request while it streams in. Over `MAX_UPLOAD_REQUEST_MB` (default 50), the request is stopped at once with 422: a declared `Content-Length` is refused before anything is read, and a chunked request is cut off at the limit, so at most that much is ever spooled. The connection is then closed. curl sends nothing at all (it waits for `100 Continue`).
- **API checks, file by file.** The size is counted while the file is copied in chunks, so an oversized file is never read into memory as a whole. The first bytes must be `%PDF-`; the extension and content type are checked but never trusted on their own. A rejected file does not stop the others.
- **Storage.** An accepted file is saved as `<upload_id>.pdf`, where `upload_id` is a random UUID, on the `uploads` volume, with a small `<upload_id>.json` that holds its original name for the worker. The job's parameters list only upload IDs and storage names, so `GET /background-jobs/{id}` never shows file names; after parsing, the original name is kept only as `candidates.source_file`, never as a path. No endpoint serves the uploads volume. The API image has no PDF or OCR libraries; it only checks and stores.
- **Worker, one file at a time.** It computes the file's SHA-256; a file already saved is logged as "duplicate file, skipped". PyMuPDF opens the file: a corrupt, password-protected or too-long (`PDF_MAX_PAGES`) file fails with a clear message, and the next file is processed.
- **Text.** PyMuPDF returns text blocks with coordinates and font sizes. A two-column page (two groups of blocks side by side, with an empty gutter between them) is read left column first, then right column; anything else top to bottom, left to right. pdfplumber extracts tables, and replaces PyMuPDF's text on a page that looks garbled.
- **OCR.** A page with almost no text (`OCR_MIN_TEXT_CHARS`) but an image is rendered at 300 DPI and read by Tesseract (`OCR_LANGUAGE`, `OCR_TIMEOUT_SECONDS` per page). If OCR is disabled, missing, times out or finds nothing, the page is flagged; a resume without usable text is flagged and no candidate is created. `parsed_with_ocr` is true when any page's text came from OCR.
- **Fields**, with simple rules: name (largest font near the top of page 1; OCR text: first non-contact line), email, phone (digits with an optional `+`), city (from `backend/app/locations/cities.json`, shared with job locations so that "Bangalore" and "Bengaluru" are the same city), current title, years of experience (an explicit "6+ years of experience", otherwise the date ranges of the Experience section merged so overlaps count once, with "Present" meaning the parse date), education entries, summary, and skills (the same taxonomy and rules as jobs; the Skills section and table cells count as skill context).
- **Validation.** `CandidateRecord` (Pydantic) checks every field. An invalid optional field becomes null with a note in `parse_warnings` ("invalid email removed"), so the candidate is still saved.
- **Saving.** A new resume with the same email (ignoring case) as an existing candidate replaces that candidate's parsed fields and skills; otherwise a new candidate is created.
- **Privacy.** Log lines identify files by the first 8 characters of their upload ID and give page numbers, but never contain file names, names, contact details or resume text. Neither do the job's parameters, Redis messages or `GET /background-jobs/{id}`. Error messages and tracebacks in the server log are reduced to the exception type and code location, and SQL parameters are never shown.

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
pip install -e ".[dev,worker]"    # worker = Playwright, PyMuPDF, pdfplumber, pytesseract; then `playwright install chromium`
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
```

The unit tests cover the crawler (BFS, normalization, robots.txt, rate limiting, retries, 429/5xx/4xx, redirects, SSRF), the extractors on saved pages in `tests/fixtures/html/`, skill extraction, job validation, and resume parsing: upload checks (signature, streamed size limit, names as data only), PDF opening (corrupt, encrypted, page limit), reading order of one- and two-column pages, tables, the garbled-text fallback, scanned-page detection and OCR failures, every candidate field (including overlapping employment dates against a fixed "today") and `CandidateRecord` validation. They never use the internet: pages come from `httpx.MockTransport`, DNS is faked, and resumes are synthetic PDFs generated by `tests/resume_pdfs.py` (invented people only; no real resume is used).

Skill extraction is measured on hand-labelled examples (LLD §6.9): job descriptions give precision 1.00 and recall 1.00; resumes give precision 1.00 and recall 0.95. The one known miss is "Swift" at the start of a sentence, which the ambiguous-word rule ignores outside a skill context.

**Database integration tests** run against a real PostgreSQL. They check:
- the migration: upgrade from an empty database, downgrade and upgrade again, models = database (`alembic check`), keys, constraints, cascades and full-precision scores;
- background jobs: the API, state rules, cancellation, progress, logs, stale-job checks and worker failures;
- saving crawled jobs and candidates (new, duplicate file, same email);
- the upload retention command against real jobs and candidates: dry run, `--delete` for every rule, and a second run that changes nothing;
- a full crawl through the API, with Celery running the real `crawl` task in-process against the mock site;
- a full resume upload through the API with the real `resume` task: accepted and rejected files, UUID storage, progress, logs, duplicates, same-email updates, cancellation between files, OCR, a broker outage, and a check that no log line contains names, contact details, file names or resume text.

They are skipped unless `TEST_DATABASE_URL` is set. With the dev override running (step 1 of *Local development*):

```bash
docker compose exec db createdb -U app matching_test     # once
cd backend
TEST_DATABASE_URL=postgresql+psycopg://app:change-me@127.0.0.1:5433/matching_test pytest
```

On Windows PowerShell, set the variable first: `$env:TEST_DATABASE_URL = "postgresql+psycopg://…/matching_test"`. The tests drop and recreate the schema of that database, so its name must end in `_test`; any other name is refused.

**OCR with the real Tesseract.** Two tests in `tests/unit/test_ocr.py` need the Tesseract program and are skipped without it. To run them in the worker image, which has it (from the repository root; `tests/` is mounted because the image does not contain it):

```bash
docker compose run --rm --no-deps -v ./backend/tests:/app/tests:ro worker \
  sh -c "pip install --user -q pytest==9.2.0 && python -m pytest -p no:cacheprovider tests/unit/test_ocr.py tests/unit/test_resume_pipeline.py"
```

## Configuration

All settings are environment variables, documented in [`.env.example`](.env.example) and read by `backend/app/config.py` (HLD §16.3).

- One `.env` in the repository root serves Docker Compose, the backend and Vite.
- Inside Docker, `docker-compose.yml` overrides `DATABASE_URL`, `REDIS_URL` and `UPLOAD_DIR` with container values (host names `db` and `redis`).
- `VITE_API_BASE_URL` and `VITE_POLL_INTERVAL_MS` are compiled into the frontend at build time. After changing them, rebuild: `docker compose up --build frontend`.
- Host-side URLs use `127.0.0.1`, not `localhost`: on Windows, psycopg can stall trying IPv6 (`::1`) first.

## Database migrations

Alembic reads `DATABASE_URL` through `app.config`. From `backend/`:

```bash
alembic revision --autogenerate -m "describe the change"   # after changing models in app/models/
alembic upgrade head                                       # apply migrations
```

The `api` container runs `alembic upgrade head` every time it starts; on an up-to-date database this does nothing.

The first migration, `alembic/versions/98acdef52211_initial_schema.py`, creates the eight tables with their keys, unique, check and partial indexes, and enables the PostgreSQL `pg_trgm` extension used by the trigram search indexes. `alembic downgrade base` removes all of it again. After changing a model, `alembic check` reports whether a new migration is needed.

## Project structure

```text
├── docker-compose.yml        # all services
├── docker-compose.dev.yml    # development only: publishes db and redis on 127.0.0.1
├── .env.example              # documented configuration, no secrets
├── backend/
│   ├── Dockerfile            # targets: api, worker
│   ├── pyproject.toml        # dependencies and pytest settings
│   ├── alembic.ini, alembic/ # database migrations (versions/: the initial schema)
│   ├── app/
│   │   ├── main.py           # FastAPI app: routers, CORS, error handlers
│   │   ├── config.py         # settings from environment variables
│   │   ├── errors.py         # standard error envelope
│   │   ├── api/              # routers: health, background_jobs; upload_limit (total upload size)
│   │   ├── schemas/          # Pydantic request/response models, JobRecord, CandidateRecord
│   │   ├── db/               # engine, sessions, Base (constraint naming)
│   │   ├── models/           # SQLAlchemy models: the eight tables of LLD Part 3
│   │   ├── services/         # background-job control (crawl and resume jobs), stale-job checks, upload retention
│   │   ├── worker/           # Celery app, crawl and resume tasks, state/progress/log helpers
│   │   ├── crawler/          # BFS frontier, fetcher, robots, rate limiter, URLs, SSRF, browser, pipeline
│   │   ├── extractors/       # plug-ins: base, registry, generic, fake_python_jobs, mock_static, mock_dynamic
│   │   ├── resumes/          # validation, text_extraction, ocr, fields, pipeline
│   │   ├── locations/        # cities.json and the city normalizer (candidates and job locations)
│   │   ├── skills/           # taxonomy.json, normalizer, extractor, sync
│   │   └── matching/         # empty until its phase
│   └── tests/                # unit/ (offline), integration/ (PostgreSQL), fixtures/html, resume_pdfs.py (synthetic PDFs)
├── mock-site/                # optional demo job site (static + JavaScript pages, robots.txt)
├── frontend/
│   ├── Dockerfile            # Node builds the app; `serve` serves the static files
│   ├── package.json, vite.config.ts, tsconfig*.json, components.json
│   └── src/
│       ├── api/client.ts     # typed API client
│       ├── components/ui/    # shadcn/ui components (button, card, badge)
│       ├── lib/utils.ts      # shadcn/ui helper
│       ├── pages/HomePage.tsx # Phase 1 landing page
│       ├── hooks/  types/
│       └── main.tsx
└── docs/                     # HLD, LLD, ADRs, diagrams
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
| A crawl seed gets 422 "private or reserved address" | The SSRF guard refuses internal hosts. Only hosts in `CRAWLER_PRIVATE_HOST_ALLOWLIST` (default `mock-site`) are exempt. |
| A crawl of a JavaScript page fails with a browser error when running the worker from the venv | Run `playwright install chromium` once (the worker image already contains Chromium). |
| An upload returns 422 "the upload is larger than 50 MB in total" | All files of one request together exceed `MAX_UPLOAD_REQUEST_MB`. Send them in several requests. (Through Docker Desktop's port forwarding on Windows, a client that does not wait for `100 Continue` may only see the answer after it stops sending; curl is answered at once.) |
| An upload returns 422 `NO_VALID_FILES` | Every file was rejected; `details.rejected_files` gives each reason (`NOT_A_PDF`: the file does not start with `%PDF-` or is declared as another type; `FILE_TOO_LARGE`: over `MAX_UPLOAD_MB`). |
| A scanned resume is flagged "OCR produced no text (Tesseract is not installed)" | The worker runs outside Docker without Tesseract. Install it, or use the worker container. |
| A resume fails with "the file has N pages; at most 20 are allowed" | Raise `PDF_MAX_PAGES` in `.env` and restart the worker. |
