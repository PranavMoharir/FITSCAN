# Learning Notes — Job–Candidate Matching Platform

These are personal study notes kept alongside the project. Each session adds the concepts covered, in plain language, with examples from this project.

- Design reference: `docs/HLD_Job_Candidate_Matching_Platform.md`
- Reasons behind each decision: `docs/ARCHITECTURE_DECISIONS.md`

---

## Session 1 — 10 November 2026: High-Level Design

### 1. What an HLD is (and is not)

- A **High-Level Design** describes the *components* of a system, *what each is responsible for* and *how they talk to each other*. It answers "what are the boxes and arrows, and why?".
- A **Low-Level Design (LLD)** comes next. It describes classes, function signatures, exact table columns and algorithms in detail.
- An HLD must separate **requirements** (what the brief demands) from **decisions** (what we chose). In our HLD these are tagged **[PDF]**, **[Decision]**, **[Assumption]** and **[Open]**. Interviewers like this, because it shows you know which parts are negotiable.

### 2. Must / Should / Could (MoSCoW prioritization)

| Priority | Meaning | In this project |
|---|---|---|
| Must | Without it, the project fails. | Job system, crawler, extractors, text resume parsing, skills, matching, API, UI, data validation |
| Should | Important, but there is a fallback. | OCR (fallback: flag scanned resumes) |
| Could | Nice extras. | Adjustable weights, embeddings, re-matching, resuming crawls, CI |

**Lesson:** never build a Could feature before every Must is done.

### 3. The architecture in one picture

```text
Browser (React) --HTTP/JSON--> FastAPI --SQL--> PostgreSQL <--SQL-- Celery worker
                                  |                                   ^
                                  +--"run job 42"--> Redis --deliver--+
```

- **React** shows the screens. It only ever talks to the API.
- **FastAPI** receives requests, validates them and either answers directly (search, matches) or creates a background job.
- **PostgreSQL** stores everything that matters: jobs, candidates, skills, matches, background jobs and logs.
- **Redis** is a queue. It only carries small messages like "please run background job 42".
- **Celery worker** is a separate process that takes messages from Redis and does the heavy work: crawling, PDF parsing, OCR and matching.

### 4. Why each technology exists (the one-line answers)

| Technology | One-line reason |
|---|---|
| React + TypeScript | Component-based UI. TypeScript catches API shape mistakes before runtime. |
| Vite | Fast dev server and build for React. |
| Tailwind + shadcn/ui | Ready, accessible components (tables, badges, progress bars) without writing much CSS. |
| FastAPI | Python web framework that generates OpenAPI docs automatically (a brief requirement) and uses Pydantic natively. |
| Pydantic | Validates and converts data: "3" becomes 3, bad emails are rejected, dates become ISO dates. |
| SQLAlchemy | Lets Python code talk to the database safely (parameterized SQL prevents SQL injection) and manages transactions. |
| PostgreSQL | Relational database: our data is full of relationships (jobs ↔ skills ↔ candidates ↔ matches). Unique constraints stop duplicates. |
| Celery | Runs Python functions in the background, in separate worker processes. |
| Redis | Fast, simple message broker for Celery. |
| httpx + BeautifulSoup | Fetch HTML and parse it. |
| Playwright | Headless browser for pages that build their content with JavaScript. |
| PyMuPDF + pdfplumber | Read PDF text with positions (PyMuPDF) and tables (pdfplumber). |
| Tesseract | OCR: reads text from images of scanned pages. |
| scikit-learn | TF-IDF text similarity, used only to order equal scores. |
| Pytest | Tests, using saved HTML and PDF files with no internet. |
| Docker Compose | Starts all containers with one command. |

### 5. Why React talks to FastAPI (and not to the database)

- The browser is **untrusted**: anyone can open developer tools. If it held database credentials, anyone could read every resume.
- The API is the **gatekeeper**. It validates input, applies business rules and decides what data to return.
- *Example:* the candidate page calls `GET /candidates/{id}/matches`. The API runs an indexed query and returns only the top 10 matches. It never returns the raw PDF.

### 6. Why PostgreSQL, and why SQLAlchemy

- **PostgreSQL** supports **relationships**. One job has many skills, and one skill appears in many jobs: a **many-to-many** relationship, implemented with the link table `job_skills`.
- **Constraints** enforce rules at the lowest level. For example, `UNIQUE(dedup_key)` makes duplicate jobs impossible even if the code has a bug.
- **Transactions** make "replace all matches" atomic: readers see either the old full set or the new full set, never half.
- **SQLAlchemy** is an **ORM** (Object-Relational Mapper): tables become Python classes. It always sends values as *bound parameters*, which prevents SQL injection, and the API and worker share the same models.

### 7. Why Redis and Celery are separate things

- **Redis** is a general-purpose in-memory data store. Here it acts as a **message broker**, a queue of messages. It knows nothing about Python.
- **Celery** is a **Python task framework**. It turns a function call into a message, sends it to the broker, runs worker processes that pick messages up and handles acknowledgements, retries and time limits.
- *Restaurant analogy:* Celery is the system of writing order tickets and the cooks; Redis is the ticket rail; PostgreSQL is the order book everyone reads.

### 8. How a background task moves through the system

1. User clicks **Start crawl**. React sends `POST /background-jobs/crawl`.
2. FastAPI validates the input, inserts a row in `background_jobs` with status `queued` and **commits**.
3. FastAPI publishes a Celery message containing only the job ID, then returns **202 Accepted** immediately.
4. A worker receives the message and runs `UPDATE … SET status='running' WHERE id=… AND status='queued'`. If no row changes, the job was cancelled, so it exits.
5. After each page, the worker saves results, updates progress and heartbeat, writes log rows and checks `cancel_requested`.
6. At the end it sets `completed`, `failed` or `cancelled`.
7. Meanwhile React **polls** `GET /background-jobs/{id}` and `/logs?after_id=…` to show progress.

Key ideas:

- **Asynchronous request–reply:** the API replies "accepted" immediately, and the client checks back later.
- **Commit before enqueue:** the worker must always find the row.
- **Conditional update:** prevents a race between start and cancel.
- **Cooperative cancellation:** the worker stops itself between items instead of being killed.

### 9. How the crawler uses BFS

- **BFS (breadth-first search)** visits all pages at depth 1 before any page at depth 2. It uses a **FIFO queue** (first in, first out).
- A **visited set** of **normalized** URLs makes sure each page is fetched once. Normalization means lower-case host, no `#fragment`, no tracking parameters, sorted query string and absolute URLs, so `HTTPS://Site.com/jobs?b=2&a=1#top` and `https://site.com/jobs?a=1&b=2` are treated as the same page.
- **Limits:** `max_depth` (how far from the seed) and `max_pages` (how many pages in total).
- **Politeness:**
  - an **allow-list** of domains;
  - **robots.txt**, the site's rules for bots;
  - a **rate limit** (a minimum gap between requests to the same domain);
  - **retries with exponential backoff** for timeouts, 429 and 5xx (wait 1 s, 2 s, 4 s…, plus random jitter).
- **Error boundary:** each page is processed inside its own `try/except`, so one bad page is logged and skipped while the crawl continues.
- **Extractors:** one file per website knows how to read that site's HTML. Plain HTTP is used by default; Playwright is used only if the page needs JavaScript.

### 10. How PDF parsing works

1. **Validate at upload:** size at most 20 MB, and the file must start with `%PDF-`.
2. **Open with PyMuPDF.** A failure means the file is corrupt; `is_encrypted` means it is password-protected. Either way the file gets a clear message, and the other files continue.
3. **Text with coordinates:** PyMuPDF returns text *blocks* with positions. If blocks cluster into a left and a right group, the page is two-column, so we read the left column first, then the right.
4. **Tables:** pdfplumber extracts table cells, which catches "skills in a table" layouts.
5. **Scanned page?** If a page has almost no text but has images, render it to an image and run **Tesseract OCR**, then set `parsed_with_ocr = true`. If OCR fails, flag the file.
6. **Fields:**
   - regular expressions for email and phone;
   - the largest font near the top for the name;
   - section headings for experience, education and skills;
   - years of experience from date ranges, merging overlaps.
7. **Validate with Pydantic**, then save.

### 11. How the matching engine calculates scores

```text
score = 70 × (required skills matched / total required)
      + 15 × (nice-to-have matched / total nice-to-have)
      + 10 × experience fit          (min(1, years / minimum))
      +  5 × location fit            (same city or remote = 1)
```

Worked example from the HLD:

- **Job:** requires Python, FastAPI, PostgreSQL and Docker. Nice-to-have: Redis and Kubernetes. Minimum 3 years. Location: Pune.
- **Candidate:** Python, FastAPI, PostgreSQL, Redis and Git; 2 years; Pune.
- **Score:** 70 × 3/4 = 52.50; 15 × 1/2 = 7.50; 10 × 2/3 = 6.67; 5 × 1 = 5.00. **Total = 71.67.**
- **Matched skills:** Python, FastAPI, PostgreSQL, Redis. **Missing skills:** Docker, Kubernetes.

Edge cases:

- No nice-to-have skills listed → full 15 points.
- No required skills found → 0 for that part, with a warning in the explanation.
- No minimum experience → full 10 points.
- Candidate's experience unknown → 0 experience points.

Skills are compared by **canonical name** ("ReactJS" → React), so spelling differences do not matter. **TF-IDF** similarity (scikit-learn) is only used to order equal scores. It is never added to the score, so the score stays explainable.

### 12. Other concepts met in this session

| Concept | Plain meaning | Where it appears |
|---|---|---|
| Idempotent upsert | Writing the same record twice leaves one record. | Jobs and candidates (`ON CONFLICT … DO UPDATE`) |
| Source of truth | The one place whose data wins. | PostgreSQL for job status |
| SSRF | Tricking a server into requesting internal addresses. | Crawler refuses private IPs (except the mock site) |
| Streaming response | Sending a file in chunks instead of building it all in memory. | CSV/JSON exports |
| Composite primary key | A key made of two columns. | `matches (candidate_id, job_id)` |
| Index | A lookup structure that makes queries fast. | `matches (candidate_id, score DESC)` for the top 10 |
| Health check | An endpoint or command that says "I am up". | `/health`, `pg_isready` in Compose |
| Test fixture | Saved input data for tests. | `tests/fixtures/html`, `tests/fixtures/pdf` |

---

## Interview questions with answers

1. **Why did you use a background worker instead of doing the crawl inside the API request?**
   - A crawl can take minutes: network waits, rate limits, retries.
   - Inside a request it would hit HTTP timeouts, tie up a server worker and be lost if the browser closed.
   - Instead, the API creates a background job, returns **202 Accepted** with its ID, and a Celery worker does the work while the UI polls for progress. This is the asynchronous request–reply pattern.

2. **How do you prevent a race between cancelling a job and the worker starting it?**
   - Every state change is a **conditional update**. The worker claims a job with `UPDATE … SET status='running' WHERE id=:id AND status='queued'`. If the API already set it to `cancelled`, zero rows change and the worker exits.
   - For running jobs, the API only sets `cancel_requested`, and the worker stops itself between items. This is cooperative cancellation, which avoids killing a process mid-write.

3. **How is the match score explainable, and where does scikit-learn fit?**
   - The score is the brief's linear formula. Every component (required, nice-to-have, experience, location) is stored as a ratio and points in `score_breakdown`, along with matched and missing skill lists and a generated sentence.
   - scikit-learn computes TF-IDF cosine similarity between the job description and the resume text. It is used **only to break ties**, so the 0–100 score always equals the sum of the visible components.

4. **How do you guarantee "no duplicates"?**
   - At three levels: normalization, database constraints and upserts.
   - Jobs get a `dedup_key` (normalized apply URL, otherwise a hash of source, title, company and location) with a UNIQUE constraint and `INSERT … ON CONFLICT DO UPDATE`.
   - Candidates are unique by file SHA-256 and upserted by email.
   - Skill links and matches use composite primary keys.
   - The constraints are the safety net even if application code has a bug.

5. **What happens if one page in a crawl returns 500 errors or malformed HTML?**
   - Each page is processed inside its own error boundary.
   - A 5xx is retried with exponential backoff and jitter. After the last attempt the page is marked failed, a WARNING or ERROR log is written and the failed counter increases.
   - Malformed HTML is tolerated by BeautifulSoup. If the extractor still fails, only that page is skipped.
   - The crawl continues and ends `completed` with failure counts. Only job-level problems, such as a disallowed seed, end it as `failed`.

---

## Test your understanding (try before reading the answer key)

1. Why does the API commit the `background_jobs` row *before* publishing the Celery message? What could go wrong otherwise?
2. A job description lists no nice-to-have skills. A candidate has every required skill, enough experience and lives in the same city. What score do they get, and why?
3. Why does the HLD use `/background-jobs` instead of `/jobs` for crawl and resume work?
4. A user searches for the skill "js". Which component turns this into "JavaScript", and why is it the same component used for resumes and job descriptions?
5. Why can't the browser read the database directly, and which two protections does the API layer provide against malicious input?

<details>
<summary>Answer key (open after attempting)</summary>

1. The worker might receive the message before the row exists, find nothing and fail (or silently skip the job). Committing first guarantees the worker can always load the job's parameters.
2. 100: 70 × 1 + 15 × 1 (an empty nice-to-have list gets full credit, by the edge-case rule) + 10 × 1 + 5 × 1. Without that rule a perfect candidate could only reach 85.
3. The required route `GET /jobs/{id}/matches` makes `/jobs` mean job postings. Reusing it for background work would be ambiguous.
4. The skill normalizer, using the taxonomy's aliases. Using one normalizer everywhere guarantees that jobs, resumes and searches all speak the same canonical skill names, so they match.
5. The browser is untrusted. Database credentials in it would expose all data. The API provides Pydantic input validation and parameterized SQL through SQLAlchemy (SQL-injection protection), plus SSRF checks, size limits and PDF verification for crawler and upload input.

</details>

---

## Next session (planned)

- Low-Level Design: SQLAlchemy models, Pydantic schemas, the extractor interface and the Celery task signatures.
- Concepts to learn: database migrations (Alembic), dependency injection in FastAPI, and Celery task acknowledgement (`acks_late`).
