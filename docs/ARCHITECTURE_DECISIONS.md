# Architecture Decision Records — Job–Candidate Matching Platform

**Version 1.1 · 12 November 2026 · Companion to `HLD_Job_Candidate_Matching_Platform.md`**

**Changes in 1.1:** ADR-017 adds the score-precision rule. ADR-019 records the measured scale path. Both correspond to Sections 10.5, 10.7 and 10.10 of the detailed HLD (`HLD_Job_Candidate_Matching_Platform_Full.md`).

This file records *why* the HLD makes each design choice. ADR numbers match the rows of the decision table in Section 20.1 of the detailed HLD (`HLD_Job_Candidate_Matching_Platform_Full.md`), so ADR-007 is row 7. The concise HLD lists the key decisions in its Section 9.

Each record states its **source**:

- **Required**: the brief mandates it, so this record only explains how it is applied.
- **Choice**: an architectural decision made in the HLD, not stated in the brief. It can be revisited.

All records have status **Proposed**. They become **Accepted** once implementation confirms them, or **Superseded** if they are replaced; when that happens, the change is recorded here.

## Index

| ADR | Title | Source |
|---|---|---|
| 001 | Modular monolith with a separate worker process | Choice |
| 002 | "Background jobs" vs "jobs" naming | Choice (forced by a required route) |
| 003 | PostgreSQL is the source of truth for job state | Choice |
| 004 | Task messages carry only an ID | Choice |
| 005 | Background-job lifecycle | Required |
| 006 | Cooperative cancellation and conditional transitions | Choice |
| 007 | Polling for live progress | Choice |
| 008 | Polite BFS crawler | Required |
| 009 | robots.txt failure policy | Choice |
| 010 | Per-crawl rate limiter | Choice |
| 011 | Extractor plug-in discovery and rendering mode | Required behavior, chosen mechanism |
| 012 | SSRF protection with a mock-site exception | Choice |
| 013 | Division of work between PDF libraries | Stack fixed, division chosen |
| 014 | OCR with a flagging fallback | Explicitly allowed |
| 015 | Own skills taxonomy | Choice within a requirement |
| 016 | Baseline scoring formula unchanged | Choice (explainability required) |
| 017 | Scoring edge-case rules | Choice |
| 018 | TF-IDF only as a tie-breaker | Choice |
| 019 | Precomputed all-pairs matches via a `match` job | Requirement + chosen mechanism |
| 020 | De-duplication keys | Requirement + chosen keys |
| 021 | UUID primary keys | Choice |
| 022 | Storage of uploaded resumes | Choice |
| 023 | One backend image, two build targets | Choice |
| 024 | Optional mock job site | Allowed by the brief |
| 025 | Matched/missing skills stored as JSONB | Choice |
| 026 | Partial-failure semantics | Choice |
| 027 | No API version prefix | Choice |
| 028 | Real and demo sources; stored industry per job | Choice |

---

## ADR-001 — Modular monolith with a separate worker process

- **Context.** The brief requires background jobs, an API, a UI and `docker compose up`. One developer builds the system and must be able to explain all of it.
- **Decision.** Use one Python backend codebase with domain modules (crawler, extractors, resumes, skills, matching). It runs as two kinds of process, a FastAPI server and Celery workers. The React SPA is a separate codebase.
- **Alternatives considered.**
  - Microservices per domain: rejected. They add network hops, deployment complexity and distributed-data problems with no scaling or team-ownership benefit here.
  - Doing the work inside API requests: rejected. It would cause timeouts and block other users.
- **Consequences.** Shared models and schemas with no duplication. Heavy work is isolated from user requests. API and workers can be scaled independently later.

## ADR-002 — "Background jobs" vs "jobs" naming

- **Context.** The brief uses "job" for both job postings and asynchronous work. The required route `GET /jobs/{id}/matches` fixes `/jobs` to mean postings.
- **Decision.** Use "background job" for asynchronous work (`background_jobs` table, `/background-jobs` API) and "job" for job postings (`jobs` table, `/jobs` API).
- **Alternatives considered.**
  - `/tasks` or `/runs`: acceptable, but less obviously linked to the brief's "jobs".
  - Sharing `/jobs` for both: ambiguous and error-prone.
- **Consequences.** Every document and endpoint is unambiguous. The terminology is defined in HLD Section 1.3.

## ADR-003 — PostgreSQL is the source of truth for job state

- **Context.** Celery can store task results in a result backend (often Redis), but the UI needs status, progress, counters and logs that survive restarts and can be queried.
- **Decision.** Workers write status, progress, heartbeat and logs to PostgreSQL. The API reads them only from PostgreSQL. Celery's result backend is not relied on.
- **Alternatives considered.** The Celery result backend for status: rejected. It is not designed for listing, filtering or log history, and it is lost if Redis is flushed.
- **Consequences.** One place to look. Progress queries are plain SQL. Redis becomes disposable infrastructure.

## ADR-004 — Task messages carry only an ID

- **Context.** Task messages pass through Redis. Crawl configurations and file lists are already stored in the `background_jobs` row.
- **Decision.** Each Celery task receives only `background_job_id` and loads its parameters from the database.
- **Alternatives considered.** Passing full parameters or file contents in the message: rejected. It makes messages larger, puts personal data in the broker and creates two sources of truth.
- **Consequences.** Messages are small. No resume data is in Redis. Re-running a job only needs its ID.

## ADR-005 — Background-job lifecycle (Required)

- **Context.** The brief requires the status flow queued → running → completed / failed / cancelled.
- **Decision.** Store exactly these five lower-case values with a CHECK constraint. Terminal states are final.
- **Consequences.** The UI can render a fixed set of status badges. The worker only claims jobs that are still queued (ADR-006).

## ADR-006 — Cooperative cancellation and conditional transitions

- **Context.** Users must be able to cancel jobs. A job might be cancelled while still in the queue or while running.
- **Decision.**
  - A queued job is cancelled directly by the API, which also revokes the Celery task as a best effort.
  - A running job gets `cancel_requested = true`. The worker checks the flag between items and stops cleanly.
  - Every state transition is a conditional `UPDATE … WHERE status = <expected>`.
- **Alternatives considered.** Forced termination (`revoke(terminate=True)`): rejected. It can interrupt database writes or leave browsers running.
- **Consequences.** There is no race between "start" and "cancel". Partial results are kept. Cancellation latency is at most one item (one page, file or candidate).

## ADR-007 — Polling for live progress

- **Context.** The UI must show live progress and logs.
- **Decision.** The UI polls `GET /background-jobs` and `GET /background-jobs/{id}/logs?after_id=…` at a short configurable interval while jobs are active.
- **Alternatives considered.** WebSockets or Server-Sent Events: they give lower latency but need connection management and extra failure handling. Neither is needed for this UI.
- **Consequences.** The UI is simple and testable. Incremental `after_id` keeps each poll small. SSE could be added later without changing the data model.

## ADR-008 — Polite BFS crawler (Required)

- **Context.** The brief requires all of the following: BFS from a seed with `max_depth` and `max_pages`; allow-listed domains; URL normalization; each URL fetched once; automatic robots.txt; per-domain rate limiting; retries for timeouts, 429 and 5xx with backoff; one bad page never crashing a job.
- **Decision.** The crawler uses:
  - a FIFO frontier of `(url, depth)` and a visited set of normalized URLs;
  - a per-host robots.txt cache and a per-domain minimum interval;
  - exponential backoff with jitter, honoring `Retry-After`;
  - a per-page error boundary.
- **Consequences.** Behavior is deterministic and testable with a mock HTTP transport. Exact normalization rules are documented in HLD Section 8.5.

## ADR-009 — robots.txt failure policy

- **Context.** robots.txt can be missing (4xx) or unreachable (5xx or timeout). The brief requires enforcement but does not define these cases.
- **Decision.** A 4xx response means no restrictions. A 5xx response or an unreachable robots.txt means the domain is treated as disallowed for this crawl, and this is logged.
- **Alternatives considered.** Treating unreachable as allowed: rejected as less polite.
- **Consequences.** It is conservative: a temporarily broken robots.txt stops the crawl of that domain, with a clear log message.

## ADR-010 — Per-crawl rate limiter

- **Context.** Rate limiting is required per domain. Two crawls could target the same domain at the same time.
- **Decision.** The limiter lives inside each crawl task. Pages within a crawl are fetched sequentially.
- **Alternatives considered.** A Redis-based shared limiter across workers: more correct under concurrency, but more complex.
- **Consequences.** Simple. Simultaneous crawls of the same domain can exceed the per-domain rate. This is documented as a known limitation, and the Redis limiter is the upgrade path.

## ADR-011 — Extractor plug-in discovery and rendering mode

- **Context.** The brief requires that adding a site means adding one new file, plain HTTP by default and a headless browser only when needed.
- **Decision.**
  - Extractors implement a small contract (`name`, `domains`, `render_mode`, `matches`, `needs_browser`, `parse`).
  - A registry auto-imports every module in `extractors/`.
  - Static fetching (httpx + BeautifulSoup) is the default. Playwright is used when `render_mode = "browser"` or `needs_browser()` returns true.
  - A generic schema.org `JobPosting` JSON-LD extractor is the fallback.
- **Consequences.** No registry edits when adding a site. Extractors are pure parsing functions, which are easy to test with saved HTML.

## ADR-012 — SSRF protection with a mock-site exception

- **Context.** A crawler that accepts user-supplied URLs can be abused to reach internal services (Server-Side Request Forgery, SSRF). The optional mock site runs on the Docker-internal network, which is a private address.
- **Decision.** Resolve every host, including redirect hops and Playwright sub-requests. Refuse private, loopback, link-local, multicast and reserved addresses. Allow only hosts listed in `CRAWLER_PRIVATE_HOST_ALLOWLIST` (for example `mock-site`).
- **Consequences.** Crawling is safe by default. The demo stays self-contained. DNS-rebinding edge cases are mitigated by checking the resolved address at connect time where possible.

## ADR-013 — Division of work between PDF libraries

- **Context.** The stack fixes PyMuPDF, pdfplumber and Tesseract. Each has different strengths.
- **Decision.**
  - PyMuPDF: opening and validating files, encryption detection, text blocks with coordinates and font sizes, and rendering pages for OCR.
  - pdfplumber: tables, and a fallback word-level extraction.
  - Tesseract: OCR of image-only pages.
- **Consequences.** Two-column detection uses block coordinates. Name detection uses font size. Skills-in-a-table layouts are captured.

## ADR-014 — OCR with a flagging fallback

- **Context.** The brief marks OCR as **Should** and allows "OCR scanned resumes (or flag them)".
- **Decision.** Detect low-text pages with images and OCR them with Tesseract (`parsed_with_ocr = true`). If OCR is unavailable or yields no text, flag the file with a clear message.
- **Consequences.** The demo's scanned resume works. Environments without Tesseract still behave correctly.

## ADR-015 — Own skills taxonomy

- **Context.** The brief allows "your own skills list or a taxonomy such as ESCO".
- **Decision.** Keep a curated, version-controlled `taxonomy.json` (canonical name → aliases, category), synchronized into the `skills` table at start-up.
- **Alternatives considered.** Importing the full ESCO taxonomy: broader coverage, but large and noisy for a tech-job demo.
- **Consequences.** Small, reviewable and testable. ESCO can later be imported into the same structure. Unknown skills are not extracted, which is a documented limitation.

## ADR-016 — Baseline scoring formula unchanged

- **Context.** The brief offers the formula `70·required + 15·nice + 10·experience + 5·location` and allows changes if the score stays explainable.
- **Decision.** Use the formula exactly, with weights held in configuration.
- **Consequences.** Every point is traceable. Adjustable weights (Could) are implemented this way (22 November 2026): the formula is unchanged; each match run takes optional whole-number weights that add up to exactly 100 (refused otherwise, never rescaled) and records them in its `params`; `MATCH_WEIGHTS` stays the default.

## ADR-017 — Scoring edge-case rules

- **Context.** The formula is undefined for empty skill lists, and the brief only says "scaled down below" the minimum experience. It also does not say how precisely scores are compared when ranking.
- **Decision.**
  - Nice-to-have list empty, required skills present: ratio 1.
  - Required list empty, nice-to-have skills present: required ratio 0, flagged in the explanation; nice-to-have ratio as usual.
  - No skills at all (both lists empty): required ratio 0 **and** nice-to-have ratio 0, flagged in the explanation. The job scores at most 15 (experience and location). This settles HLD open question O2 (decided 19 November 2026).
  - No minimum experience: experience fit 1.
  - Unknown candidate experience with a minimum set: fit 0.
  - Experience fit is linear: `min(1, years / minimum)`.
  - Location fit is 1 for remote jobs or the same normalized city, otherwise 0.
  - Score precision: the score is computed exactly (Python `fractions.Fraction`) and stored unrounded as `DOUBLE PRECISION`. It is rounded to 2 decimals only for display: API responses, UI, explanations and exports. Ranking, `rank` and the top-10 cut use the unrounded value.
- **Alternatives considered.**
  - For a job with no skills at all, keeping nice-to-have ratio 1 (the rule for an empty nice-to-have list). Such a job then got 15 points for nice-to-have skills it never listed, plus 10 for experience when it states no minimum: 25 points, or 30 when remote or in the candidate's city. That beat real partial matches, for example 1 of 4 required skills in another city (27.5). After the 19 November 2026 recrawl, 90 of the 108 crawled jobs had no skills, so these jobs would have filled every candidate's top 10.
  - Leaving jobs without skills out of matching: it breaks "every candidate against every job" and can leave fewer than 10 results. They are still scored and stored.
  - Storing the score rounded to 2 decimals (`NUMERIC(5,2)`): rounding can make different scores equal, so the tie-breaker would decide their order.
  - Plain floating-point arithmetic: it gives mathematically equal scores slightly different values, so floating-point error would decide their order. For example, two scores of exactly 71⅔ come out as 71.66666666666667 and 71.66666666666666.
- **Consequences.**
  - Perfect candidates reach 100.
  - Jobs whose skills could not be extracted do not flood every candidate's top 10: they get no skill points at all, so they score at most 15 and rank below every job worth more than 15 points to the candidate. The rule was checked in the README's 5-candidate hand check (HLD open question O2, now decided).
  - The nice-to-have ratio of 1 for a job with required skills but no nice-to-have list also goes to a candidate who has none of the required skills: 0 + 15 + experience + location. In the hand check, this put two such jobs at a data analyst's ranks 9 and 10 (25.00). A job in his own city that lists nice-to-have skills, which he does not match either, scored 15.00. The rule is kept (confirmed 19 November 2026): the required ratio, worth 70 points, still decides the ranking, so only weak matches at the bottom of a list are reordered. The explanation states it ("The job lists no nice-to-have skills").
  - Neither rounding nor floating-point error changes a ranking, and exactly equal scores always reach the tie-breaker. In a synthetic benchmark, plain floats changed the top 10 of 1 candidate in 100; exact scores changed none (detailed HLD Section 10.10).
  - Exact arithmetic is about 12× slower per pair than plain floats (0.63 s for 100,000 pairs in that benchmark). This is acceptable for a background job at assignment scale.

## ADR-018 — TF-IDF only as a tie-breaker

- **Context.** scikit-learn is in the fixed stack. Many pairs share the same score because the ratios take only a few distinct values.
- **Decision.** Compute TF-IDF cosine similarity between job description and resume text. Use it only to order equal scores, and show it separately. It never contributes to the 0–100 score.
- **Consequences.** The score stays fully explainable. Ordering within ties is meaningful and deterministic.

## ADR-019 — Precomputed all-pairs matches via a `match` job

- **Context.** The brief requires scoring every candidate against every job and showing the top 10 in both directions. Automatic re-matching when new jobs arrive is a Could feature (implemented later; see the consequences).
- **Decision.** A `match` background job computes all pairs, one pair at a time with the exact scoring function (ADR-017), and replaces the `matches` table in one transaction. It is triggered manually from the UI or API. Reads use indexes on `(candidate_id, score)` and `(job_id, score)` and order by the full-precision score, then the tie-breakers (ADR-018).
- **Alternatives considered.**
  - Computing on every request: always fresh, but repeats work and is harder to export.
  - Vectorized sparse-matrix scoring, and storing only each candidate's and each job's top 10. On synthetic data these were about 15× faster and stored 90–99.5% fewer rows, with identical top-10 lists. They are more complex to explain and not needed at assignment scale, so they are recorded as the scale path instead (detailed HLD Section 10.10).
- **Consequences.**
  - Match pages are fast, and exports read stored rows. Results can be stale until recomputed, so the UI shows "last computed".
  - Two runs may be in progress at once. A run saves its results and becomes `completed` in one transaction under the table lock, and only if no run that started later has already saved; otherwise it ends `cancelled` as superseded (LLD §7.9). An older run never overwrites a newer run's results.
  - Automatic re-matching (Could, implemented 22 November 2026): a crawl that ends `completed`, or `failed` after saving jobs, and saved new jobs or changed what matching reads, queues a full `match` run with the active weights. Never after a cancelled crawl, and not when `AUTO_REMATCH` is `false`, there are no candidates or a run is already queued. Manual and automatic requests take the same advisory lock, so they never race into duplicate runs; the rule above keeps an automatic run from overwriting newer results.
  - If volumes grow, the scale path is applied in this order:
    1. vectorized scoring, with its rankings first checked against the exact version;
    2. top-10-only storage;
    3. incremental recompute.

## ADR-020 — De-duplication keys

- **Context.** The brief requires "no duplicates".
- **Decision.**
  - Jobs: `dedup_key` is the normalized `apply_url`, or a hash of source, title, company and location. Writes are upserts that merge non-null fields.
  - Candidates: unique file SHA-256, plus upsert by case-insensitive email.
  - Link tables and matches: composite primary keys.
- **Consequences.** Listing and detail pages merge into one job. A re-uploaded file is detected. Two different people sharing an email address would merge, which is an accepted edge case.

## ADR-021 — UUID primary keys

- **Context.** Candidate records contain personal data, and their IDs appear in URLs.
- **Decision.** Use UUIDs for jobs, candidates and background jobs. Use integers for skills and log rows.
- **Consequences.** IDs cannot be guessed or enumerated, and they do not leak record counts. They are slightly larger than integers, which is irrelevant at this scale.

## ADR-022 — Storage of uploaded resumes

- **Context.** The API receives files and the worker parses them later.
- **Decision.** The API saves files to a shared Docker volume under random UUID names. No endpoint serves raw files. The original file name is kept only as data (`source_file`).
- **Consequences.** No path traversal. Personal documents are not exposed. The worker and API share the volume.

## ADR-023 — One backend image, two build targets

- **Context.** The worker needs Chromium (Playwright) and Tesseract. The API needs neither.
- **Decision.** One `backend/Dockerfile` with an `api` target and a `worker` target. The worker target adds the browser and OCR packages.
- **Consequences.** Shared code and dependencies, and the API image stays small.

## ADR-024 — Optional mock job site

- **Context.** The demo must scrape one static and one dynamic site. The brief allows "your mock site if you built one".
- **Decision.** Include a small `mock-site` container with a static job page and a JavaScript-rendered job page, each with its own robots.txt.
- **Consequences.** The demo is reproducible offline. Its saved pages double as test fixtures.

## ADR-025 — Matched/missing skills stored as JSONB

- **Context.** The brief requires matched skills, missing skills and an explanation for each match.
- **Decision.** Store `matched_skills` and `missing_skills` as JSONB arrays of `{skill, level}`, plus a `score_breakdown` JSONB, on each match row.
- **Consequences.** The explanation is a snapshot of the scoring run. The UI and exports need no extra joins. Data is recomputed on the next match run.

## ADR-026 — Partial-failure semantics

- **Context.** One bad page or file must not crash a job, but the final status must still be meaningful.
- **Decision.** If any item succeeded, the job ends `completed` and shows succeeded and failed counts. It ends `failed` only on a job-level error or when every item failed.
- **Consequences.** Users see partial success clearly. Total failure is not hidden behind "completed".

## ADR-027 — No API version prefix

- **Context.** The brief specifies exact paths such as `GET /candidates/{id}/matches`.
- **Decision.** Serve routes without a `/api/v1` prefix.
- **Consequences.** The paths match the brief exactly. If versioning is ever needed, a prefix can be added together with redirects.

## ADR-028 — Real and demo sources; stored industry per job

- **Context.** The brief allows real job sources, generated data or both. FITSCAN collects real openings from company career pages and job-board APIs and keeps its demo sites, across industries, not only IT. Users must never mistake an invented job for a real opening, and must be able to browse by industry.
- **Decision (22 November 2026).** (1) Real versus demo is derived from `jobs.source`: each extractor declares `demo`, a job is real only if its source is a real-source extractor, and the crawler takes jobs from a demo host only through its demo extractor; no column is added for it. (2) The industry is computed by explainable rules (title terms, skill categories, description terms; Other / Unclassified when the evidence is weak or tied) when a job is saved, and stored in a new `jobs.industry` column, indexed and checked against the 13 codes. (3) JSON job-board APIs (Greenhouse, Lever) are read by ordinary extractor plug-ins through the same crawler.
- **Alternatives considered.**
  - A stored `is_demo` flag: the source already says it, and a flag could disagree with it.
  - Classifying the industry on every request: it cannot be filtered, counted or paged in SQL, and would break the one-query-per-page search (LLD §4.4).
  - Keyword rules in SQL, or a trained classifier: hard to explain and test, or a new dependency and training data.
- **Consequences.**
  - The Jobs filters, counts and exports stay plain SQL; the job page shows the evidence for the industry.
  - The migration fills the industry of existing jobs once; when the rules change, a job is reclassified on its next crawl, or at once with `python -m app.services.reclassify --apply`, which writes only `jobs.industry` (the job page says when the current rules would classify it differently).
  - Industries never affect matching; real and demo jobs are scored by the same engine.
  - A removed extractor's old jobs count as demo, never as real.
