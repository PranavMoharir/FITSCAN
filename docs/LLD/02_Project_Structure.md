# 2. Project Structure

> **Status: Planned.** Section 2.1 shows what exists today. Section 2.2 shows the planned layout from HLD §17.

## 2.1 What Exists Today

On 18 November 2026 the repository contains documentation only:

```text
FITSCAN/
├── LEARNING_NOTES.md                         # architecture learning notes
└── docs/
    ├── HLD_Job_Candidate_Matching_Platform.md        # concise HLD (v1.2)
    ├── HLD_Job_Candidate_Matching_Platform_Full.md   # detailed HLD (v1.2)
    ├── HLD_Job_Candidate_Matching_Platform.docx      # Word export of the detailed HLD (v1.2)
    ├── ARCHITECTURE_DECISIONS.md                     # ADR-001 to ADR-027
    ├── diagrams/                                     # Mermaid sources + PNG/SVG renders
    ├── pdf/                                          # PDF exports of the documents
    ├── archive/                                      # earlier versions: HLD v1.1 (+ old diagrams 06 and 08), v1.0 exports
    └── LLD/                                          # this Low-Level Design
```

## 2.2 Planned Layout

The folders and what each one contains come from HLD §17. **File names inside the folders are proposed names** introduced by this LLD (**LLD decision** LLD-1), so that later parts can say exactly where each piece of logic lives. Each file name follows a responsibility that HLD §17 lists for that folder.

```text
<repo-root>/
├── docker-compose.yml            # all services
├── .env.example                  # documented configuration, no secrets
├── README.md · DATA_SOURCES.md · AI_USAGE.md   # deliverables required by the brief
├── backend/
│   ├── Dockerfile                # two targets: api, worker (adds Playwright + Tesseract)
│   ├── pyproject.toml
│   ├── alembic/                  # database migrations
│   ├── app/
│   │   ├── main.py               # creates the FastAPI app: routers, CORS, error handlers
│   │   ├── config.py             # settings read from environment variables
│   │   ├── api/                  # routers (one file per resource)
│   │   │   ├── background_jobs.py · jobs.py · candidates.py
│   │   │   ├── exports.py · skills.py · health.py
│   │   │   └── upload_limit.py      # total size limit of an upload request, while it streams in
│   │   ├── schemas/              # Pydantic request/response models and record schemas
│   │   │                         # (e.g. job.py: JobRecord, candidate.py: CandidateRecord)
│   │   ├── models/               # SQLAlchemy models, one class per table
│   │   ├── db/                   # engine and session management
│   │   ├── services/             # business rules that use the database
│   │   │   ├── background_jobs.py   # create, list, cancel background jobs
│   │   │   ├── search.py            # filtered, paginated job/candidate queries
│   │   │   ├── matches.py           # top-10 match queries
│   │   │   ├── export.py            # CSV/JSON streaming
│   │   │   └── upload_retention.py  # manual clean-up of uploads no longer needed (Part 6)
│   │   ├── worker/               # the only code that knows about Celery
│   │   │   ├── celery_app.py        # Celery application and settings
│   │   │   ├── tasks.py             # crawl, resume and match task entry points
│   │   │   └── progress.py          # progress, heartbeat and log helpers
│   │   ├── crawler/
│   │   │   ├── frontier.py          # BFS loop: queue, visited set, limits, per-page pipeline
│   │   │   ├── fetcher.py           # httpx fetching with retries and redirects
│   │   │   ├── robots.py            # robots.txt cache and checks
│   │   │   ├── rate_limiter.py      # per-domain minimum interval
│   │   │   ├── urls.py              # URL normalization and allow-list checks
│   │   │   └── ssrf.py              # private-address guard
│   │   ├── extractors/
│   │   │   ├── base.py              # plug-in contract, ExtractionResult, RawJob
│   │   │   ├── registry.py          # auto-discovery and selection
│   │   │   ├── generic.py           # fallback: schema.org JobPosting JSON-LD
│   │   │   └── <site>.py            # one file per supported website
│   │   ├── resumes/
│   │   │   ├── validation.py        # signature, size, encryption, corruption checks
│   │   │   ├── text_extraction.py   # text blocks, column order, tables
│   │   │   ├── ocr.py               # scanned-page detection and Tesseract OCR
│   │   │   ├── fields.py            # sections and candidate fields
│   │   │   └── pipeline.py          # from a stored PDF to a saved candidate; duplicate rules
│   │   ├── locations/
│   │   │   ├── cities.json          # known cities and their other spellings
│   │   │   └── normalizer.py        # text → canonical city (candidates and job locations)
│   │   ├── skills/
│   │   │   ├── taxonomy.json        # canonical skills and their aliases
│   │   │   ├── normalizer.py        # alias → canonical name
│   │   │   └── extractor.py         # finds skills in text; required vs nice-to-have
│   │   └── matching/
│   │       ├── scoring.py           # the formula and edge-case rules (exact arithmetic)
│   │       ├── explanation.py       # breakdown and explanation sentence
│   │       ├── ranking.py           # ordering and tie-breakers
│   │       ├── tfidf.py             # TF-IDF text similarity (tie-breaker only)
│   │       └── engine.py            # loads data, scores all pairs, saves results
│   └── tests/
│       ├── fixtures/html/        # saved static and rendered pages
│       ├── resume_pdfs.py        # synthetic resume PDFs, generated while the tests run (Part 9)
│       ├── unit/
│       └── integration/
├── frontend/
│   ├── Dockerfile · package.json · vite.config.ts · tsconfig.json · components.json
│   └── src/
│       ├── api/                  # typed API client
│       ├── components/ui/        # shadcn/ui components
│       ├── components/           # shared app components: skill badges, progress, log viewer
│       ├── pages/                # the six pages (Part 8)
│       ├── hooks/                # polling and data-loading hooks
│       └── types/                # TypeScript types mirroring the API schemas
├── mock-site/                    # Optional: static + JavaScript-rendered job pages
├── scripts/                      # development tools, e.g. fake resume generation
└── samples/                      # exported jobs, candidates and match table (deliverable)
```

## 2.3 Module Responsibilities

| Folder | Responsibility | Runs in | Details |
|---|---|---|---|
| `app/api` | Receive HTTP requests, validate input, call a service, return a schema. No business logic. | API | Part 4 |
| `app/schemas` | Pydantic models: the contract between frontend and backend, plus `JobRecord` and `CandidateRecord` for extracted data. | API, worker | Parts 4–6 |
| `app/models`, `app/db` | SQLAlchemy models, engine and one session per request or task. The only layer that knows table structure. | API, worker | Part 3 |
| `app/services` | Background-job control, search, match queries and export: rules that need the database. | API | Part 4 |
| `app/worker` | Celery app and thin task wrappers that call the domain modules; progress and log helpers. | Worker | Part 5 |
| `app/crawler` | Polite, bounded BFS crawl and the per-page job pipeline. | Worker | Part 5 |
| `app/extractors` | Site-specific parsing of HTML into raw jobs and links. Never touches the database. | Worker | Part 5 |
| `app/resumes` | PDF checks, text and layout extraction, OCR and field extraction. | Worker (quick checks also in API) | Part 6 |
| `app/locations` | The city list and normalizer, shared by candidates and job locations, so "Bangalore" and "Bengaluru" are one city. Standard library only. | API, worker | Parts 6–7 |
| `app/skills` | The taxonomy, the normalizer and the skill extractor, shared by jobs, resumes and search. | API, worker | Part 6 |
| `app/matching` | Scoring, explanations, TF-IDF tie-breaker, ranking, and the match run. | Worker (ranking order also used by API queries) | Part 7 |
| `frontend/src` | React pages, components, typed API client and polling hooks. | Browser | Part 8 |
| `backend/tests` | Offline unit and integration tests with saved fixtures. | Test run | Part 9 |

## 2.4 Dependency Rules

These rules keep the code easy to test and explain (HLD §8.2):

1. **Routers → services → models.** A router never writes SQL itself; it calls a service.
2. **Domain modules have no web framework code.** `crawler`, `extractors`, `resumes`, `skills` and `matching` never import FastAPI, so the worker can reuse them directly.
3. **Only `worker/` imports Celery.** Tasks are thin wrappers around the domain modules.
4. **Extractors are pure parsers.** They take a URL and HTML and return data; the crawler saves it.
5. **The frontend talks to the backend only over HTTP.** It has no access to the database, Redis or the worker.
