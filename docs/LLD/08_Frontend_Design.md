# 8. Frontend Design

> **Status: Planned.** The pages, components and polling rules come from HLD §8.1. Folders follow Part 2 (`frontend/src`).

## 8.1 Overview

The frontend is a **React + TypeScript single-page application (SPA)**:

- **Vite** builds it, and the `frontend` container serves the built static files.
- **Tailwind CSS** and **shadcn/ui** provide the styling and components.
- **React Router** switches between pages without reloading.

The browser loads the app once, then calls the FastAPI API **directly** over HTTP with JSON. The API address comes from the build-time variable `VITE_API_BASE_URL`, and the API's CORS setting allows only this frontend's origin. The frontend never talks to the database, Redis or the worker.

The brief says "simple is fine", so the UI uses plain tables, badges and forms.

## 8.2 Pages

Each page is one component in `src/pages/`:

| Route | Page | What it shows and does |
|---|---|---|
| `/` | Landing page | The public FITSCAN marketing page: what the platform does, an interactive product preview built on sample data (no API calls), and links into the application. Unknown paths redirect here. |
| `/app` | Dashboard | The entry point into the FITSCAN application, linked from the landing page. Counts of jobs, candidates and skills; background jobs by status with live progress; recent runs; the last completed run of each step; system status (API, PostgreSQL and Redis, from `GET /health`). |
| `/background-jobs` | Background jobs | Table of background jobs: type, status badge, progress bar, timestamps. "New crawl" form (seed URL, `max_depth`, `max_pages`, allowed domains). "Upload resumes" dialog (several files at once). "Recompute matches" button. Cancel button on active jobs. |
| `/background-jobs/:id` | Background job detail | The job's parameters (a match run queued by a crawl names and links that crawl), succeeded and failed counters, failure reason if any, and a live log viewer with a level filter |
| `/jobs` | Jobs | Searchable, paginated table: title, company, location, job type, posted date, required skills. Export CSV / JSON buttons. |
| `/jobs/:id` | Job detail | Job fields, then the top 10 candidates. Each shows the score, matched (tinted, with a check) and missing (dashed, with a minus) skill badges by level, and the explanation. |
| `/candidates` | Candidates | Searchable, paginated table: name, current title, city, years of experience, skills, OCR flag. Export CSV / JSON buttons for the candidates, plus "Export match table" (CSV / JSON) for the same candidates' top 10 jobs. |
| `/candidates/:id` | Candidate detail | Candidate fields, any parse warnings, then the top 10 jobs, presented the same way as on the job detail page |
| `/matching` | Matching | Scoring formula with the active weights (and the weights of the current results when they differ or were not recorded), latest match run (live while it runs), "Recompute matches" with the weights form, and a search to open any candidate's or job's top matches. |
| `/skills` | Skills | Canonical skills from `GET /skills` by category, each linking to Jobs and Candidates filtered by that skill. |
| `/exports` | Exports | Full CSV/JSON downloads of jobs, candidates and the match table (jobs per candidate selectable); filtered exports stay on Jobs and Candidates. |

## 8.3 Components

| Kind | Components | Location |
|---|---|---|
| shadcn/ui building blocks | Table, Badge, Progress, Dialog, Input, Button, Tabs, Card, Toast | `src/components/ui/` |
| Shared app components | Skill badges (matched: tinted, with a check; missing: dashed, with a minus; each with the level), job progress bar, log viewer | `src/components/` |
| Data hooks | Polling hook for job status and logs; data-loading hooks for lists and detail pages | `src/hooks/` |
| Types | TypeScript interfaces that mirror the API's Pydantic schemas | `src/types/` |

## 8.4 Communication with FastAPI

**Typed API client** (`src/api/`). One module:

- wraps `fetch` and holds the base URL;
- exposes one typed function per endpoint, for example `getCandidateMatches(id)`;
- converts the API's error envelope (`{"error": {code, message, details}}`) into a typed error object, so every page shows errors the same way.

The TypeScript types can be generated from the API's OpenAPI document, so a change in the backend schema shows up as a TypeScript build error rather than a runtime bug.

| User action | Request |
|---|---|
| Submit the crawl form | `POST /background-jobs/crawl` (JSON) |
| Upload resumes | `POST /background-jobs/resume` (`multipart/form-data`, field `files`, one or more) |
| Click "Recompute matches" (weights form, filled from `GET /matching/weights`) | `POST /background-jobs/match` with `{"weights": …}` |
| Cancel a job | `POST /background-jobs/{id}/cancel` |
| Search a table | `GET /jobs` or `GET /candidates` with `q`, filters, `page`, `page_size` |
| Open a detail page | `GET /jobs/{id}` + `GET /jobs/{id}/matches`, or `GET /candidates/{id}` + `GET /candidates/{id}/matches` |
| Export a table | A plain download link to `/exports/jobs` or `/exports/candidates` with `format` and the table's current filters |
| Export the match table | On the Candidates page: a download link to `/exports/matches?format=…&top=10` with the candidates table's current filters |

**Where the match-table export lives** (**LLD decision** LLD-10; also in HLD v1.2 §8.1). The button goes on the **Candidates page**, because the match table lists each candidate's top 10 jobs. It uses the same filters as the candidates table, so "what you see is what you export" holds here too (Section 4.5). With no filters, it exports the full match table that the brief asks for in `samples/`.

**Showing errors.** Validation errors (422) appear next to the form that caused them. For an upload, the dialog lists every rejected file with its reason. The list comes from `rejected_files` when the upload was accepted (202), and from the error envelope's `details.rejected_files` when nothing was accepted (422). Other errors appear as a toast with the API's message.

## 8.5 Live Progress (Polling)

While at least one visible background job is `queued` or `running`, the UI polls **every 2 seconds** (**LLD decision** LLD-9; also in HLD v1.2 §8.1). The interval comes from the build-time variable `VITE_POLL_INTERVAL_MS` (default `2000`), read by the polling hook in `src/hooks/`. It is a setting, not a performance target. Each poll requests:

- `GET /background-jobs` refreshes status badges, progress bars and counters;
- on a job's detail page, `GET /background-jobs/{id}/logs?after_id=<last seen log_id>` fetches **only new** log lines, which are appended to the log viewer.

Polling stops when every visible job is `completed`, `failed` or `cancelled`. Polling was chosen over WebSockets or Server-Sent Events because it needs no extra infrastructure and is easy to test (ADR-007).

## 8.6 Display Rules for Matches

- Match lists are shown **in the order the API returns them**, and `rank` comes from the API. The UI never re-sorts matches by the displayed score, because the displayed score is rounded (Part 7, Section 7.6).
- The score is shown as the API sends it, with 2 decimals (for example 71.67).
- Matched and missing skills always appear, as the brief requires, with the level ("required" or "nice-to-have").
- The explanation sentence appears under each match. Text similarity is shown separately, labelled as "used to order equal scores".
- Both detail pages show when matches were last computed (`computed_at`).

## 8.7 User Workflows

| Workflow | Steps in the UI |
|---|---|
| Crawl jobs | Background jobs page → "New crawl" → fill in seed URL and limits → submit → the new job appears as `queued`, then `running` with a moving progress bar → open it to watch log lines |
| Upload resumes | "Upload resumes" → choose one or more PDFs → submit → see accepted and rejected files → watch the resume job's progress |
| Compute matches | "Recompute matches" → keep or change the weights (whole numbers that add up to exactly 100; "Reset to defaults" restores 70, 15, 10, 5) → watch the `match` job finish → detail pages show the new results and time |
| Cancel | Click Cancel on a queued or running job → it becomes `cancelled`, immediately or after the current item |
| Browse and search | Jobs or Candidates page → type a search term or a skill (for example "js", which finds JavaScript) → page through results |
| Review matches | Click a candidate → see their top 10 jobs; click a job → see its top 10 candidates, with matched (tinted, with a check) and missing (dashed, with a minus) skill badges by level |
| Export | Click Export CSV or JSON on the Jobs or Candidates table → the browser downloads the file with the same filters as the table. On the Candidates page, "Export match table" downloads those candidates' top 10 jobs. |
