# FITSCAN: submission summary

**Live application:** <https://fitscan-demo.duckdns.org> (the application itself is at `/app`)
**Repository:** <https://github.com/PranavMoharir/FITSCAN> (branch `main`)
**Access:** the site asks for a user name and password (HTTP Basic authentication over HTTPS). They are sent to you
separately; they are not in this repository.

## 1. What FITSCAN does

FITSCAN matches job openings with candidates. It collects jobs by crawling job sites, reads candidates from PDF resumes
(including scanned ones, through OCR), scores every candidate against every job with one weighted formula, and shows the
best 10 jobs for each candidate and the best 10 candidates for each job, each with an explanation of its score. Crawls,
resume parsing and match runs are background jobs whose progress and logs can be followed in the browser. Jobs,
candidates and the match table can be exported as CSV or JSON.

## 2. Features

- **Crawler.** Breadth-first from a seed URL within `max_depth` and `max_pages`; robots.txt, per-host rate limits,
  retries with backoff, an SSRF guard, de-duplication, and headless Chromium only for pages that need JavaScript.
  Sources: company career pages (schema.org `JobPosting`), Greenhouse and Lever boards, and two demo sites (Fake Python
  Jobs and FITSCAN's own mock site), whose jobs are always labelled demo. A crawl cut off by `max_pages` says so in its
  log.
- **Resume parsing.** PDF upload with size and signature checks; one- and two-column layouts, tables, and OCR of scanned
  pages with Tesseract; name, contact details, city, current title, years of experience, education and skills.
  Encrypted, damaged and duplicate files are reported per file.
- **Matching.** Every pair, exact scores, explanations, the TF-IDF tie-breaker, top 10 in both directions, adjustable
  weights per run (whole numbers adding up to 100).
- **Application UI.** Dashboard, background jobs (start, follow, cancel, logs), jobs, candidates, matching, skills and
  exports, on desktop, tablet and phone.
- **Operations.** Docker Compose, health checks on every service, a CI pipeline, a public deployment with HTTPS and
  daily verified database backups.

## 3. Architecture and technology

A React single-page application talks to a FastAPI REST API. Long-running work goes to a Celery worker through Redis;
all data, job progress and logs are in PostgreSQL. In production a Caddy proxy is the only public entry point.

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui |
| API | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Background work | Celery with Redis as the broker |
| Crawling | httpx, Playwright (headless Chromium) |
| Resume parsing | PyMuPDF, pdfplumber, Tesseract OCR |
| Matching | Exact fractions in Python; scikit-learn TF-IDF only to order equal scores |
| Database | PostgreSQL 17 |
| Deployment | Docker Compose; Caddy (HTTPS from Let's Encrypt) on an Oracle Cloud Always Free Arm VM |

Design documents: [HLD](docs/HLD_Job_Candidate_Matching_Platform_Full.md), [LLD](docs/LLD/README.md),
[architecture decisions](docs/ARCHITECTURE_DECISIONS.md).

## 4. Matching formula

```text
Score = 70·R + 15·N + 10·E + 5·L        (0 to 100)
```

- **R**: the share of the job's required skills that the candidate has.
- **N**: the share of the job's nice-to-have skills that the candidate has.
- **E**: experience fit, `min(1, candidate years / job minimum)`.
- **L**: 1 if the job is remote or in the candidate's city, otherwise 0.

Edge cases, fixed in the design: a job with no skills gets R = 0 and N = 0; a job with required but no nice-to-have
skills gets N = 1; a job with only nice-to-have skills gets R = 0; no minimum experience gives E = 1; a minimum with
unknown candidate years gives E = 0; hybrid jobs are city-based. Scores are stored at full precision and rounded only
for display. Exactly equal scores are ordered by TF-IDF cosine similarity of the job description and the resume text,
which never changes a score.

## 5. Database

Eight tables ([LLD Part 3](docs/LLD/03_Database_Design.md)), created by an Alembic migration: `jobs`, `skills`,
`job_skills` (required or nice-to-have), `candidates`, `candidate_skills`, `matches` (one row per candidate-job pair,
with the score breakdown and explanation), `background_jobs` and `background_job_logs`.

## 6. Testing

- **1,158 backend tests** (unit and PostgreSQL integration), all passing in GitHub Actions with none skipped, including
  OCR with the real Tesseract; the frontend type check, production build and a sidebar rendering check.
- **Independent checks on the live data (24 November 2026):** all 432 stored scores (108 jobs × 4 candidates) were
  recalculated outside the application with exact fractions and agreed; so did all 112 top-10 lists, in both
  directions, including the tie-breakers.
- **Browser checks** of every page at desktop, tablet and phone sizes (no console errors, no Content Security Policy
  violations, no layout overflow), and security checks of the live site (HTTPS, login, closed internal ports, request
  limits).

## 7. Deployment

- One Oracle Cloud Always Free virtual machine (Arm, 2 OCPUs, 4 GB), Ubuntu 24.04, at no cost.
- Six containers: PostgreSQL, Redis, API, worker, frontend and the Caddy proxy. Only the proxy is reachable from the
  internet (ports 80 and 443); everything except `GET /api/health` needs the login.
- HTTPS with a Let's Encrypt certificate, security headers, rate and size limits; the API documentation is switched off
  in production.
- The database is backed up every day, and each backup is checked before it is kept. Restoring a backup into a separate
  database has been tested.

Details: [`deploy/README.md`](deploy/README.md).

## 8. Data on the live site

All data is synthetic:

- **108 demo jobs.** 100 from Fake Python Jobs, a public practice site with generated postings, and 8 from FITSCAN's
  own mock site, with required and nice-to-have skills, minimum experience, Indian cities, and remote and hybrid jobs.
- **4 candidates** from generated resumes of invented people: a backend engineer (Pune), a frontend developer (Chennai),
  a data analyst (Bengaluru), and a scanned copy of the backend engineer's resume, read by OCR.
- **432 matches** from one match run.

## 9. How to review it

1. Open <https://fitscan-demo.duckdns.org> and enter the login you received. The landing page explains the product;
   **Get started** or **Explore the Platform** (or `/app`) opens the dashboard.
2. **Jobs**: filter by listing, industry or source, and open **Backend Python Developer**. Its top candidates show
   matched and missing skills by level and an explanation of each score.
3. **Candidates**: open **Asha Verma**. Her best match, **Go Backend Engineer**, scores 82.50:
   70 × 3/4 + 15 × 1/1 + 10 × 1 + 5 × 1 (a remote job).
4. **Matching**: the formula, the active weights and the latest run. **Background jobs**: the crawl, upload and match
   runs with their logs. The resume upload shows OCR on a scanned page and clear errors for an encrypted and a damaged
   file.
5. **Exports**: download jobs, candidates or the match table as CSV or JSON.
6. You may start a crawl (Fake Python Jobs, with **Max pages 110**) or **Recompute matches**. Please upload only
   synthetic PDFs: `cd backend && python -m tests.resume_pdfs sample-resumes` generates them. No real resume, please.

To run it locally instead: see [Quick start](README.md#quick-start-docker) in the README (Docker Desktop, two commands).
The API's interactive documentation is available locally at <http://localhost:8000/docs>.

## 10. Known limitations

- **Demo data.** 90 of the 100 Fake Python Jobs postings name no skill (the site generates filler text for many
  professions), so they score at most 15 and cannot tell candidates apart; the mock site's 8 jobs show the matching
  meaningfully.
- **Skills** come from FITSCAN's own taxonomy (147 skills) and keyword rules: a skill outside the taxonomy is not seen.
- **The score reads only skills, years of experience and city**; titles, seniority and the rest of the text only break
  exact ties. Location is remote or same city, nothing in between.
- **Matches are recomputed on request** (automatic re-matching is switched off in production).
- **Access** is one shared login at the proxy; there are no user accounts.
- **Deferred:** resuming an interrupted crawl, and embedding-based matching.

The full list is in the README's [Known limitations](README.md#known-limitations); how AI was used is in
[`AI_USAGE.md`](AI_USAGE.md).
