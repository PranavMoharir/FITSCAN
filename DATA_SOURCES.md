# Data sources

Where FITSCAN's jobs and resumes come from, how each source is read, and the rules every crawl follows.
The brief allows real sources, generated data or both; FITSCAN supports both, side by side, and always
says which is which.

## Job sources

Each source is one extractor plug-in in `backend/app/extractors/`. `GET /sources` lists them, and the
"New crawl" dialog offers them by name.

| Source | Kind | Extractor (`jobs.source`) | How it is read | Seed URL |
|---|---|---|---|---|
| Company career pages | Real | `generic` | The page's schema.org `JobPosting` data (JSON-LD), which many official career sites publish for search engines | The careers page, e.g. `https://careers.example.com/jobs` |
| Greenhouse job boards | Real | `greenhouse` | Greenhouse's public Job Board API (JSON, no login or key): one request lists the board's open jobs with their descriptions | `https://boards-api.greenhouse.io/v1/boards/<board token>/jobs?content=true` |
| Lever job boards | Real | `lever` | Lever's public Postings API (JSON, no login or key): one request lists the published postings | `https://api.lever.co/v0/postings/<company>?mode=json` |
| FITSCAN mock site | Demo | `mock_static`, `mock_dynamic` | The bundled `mock-site` container: static pages, and one page whose jobs appear only after JavaScript runs (rendered in headless Chromium) | `http://mock-site:8080/static/index.html` (inside Docker) |
| Fake Python Jobs | Demo | `fake_python_jobs` | Real Python's public practice site; its jobs and companies are generated | `https://realpython.github.io/fake-jobs/` |

The board token is the name in `boards.greenhouse.io/<token>` (or `job-boards.greenhouse.io/<token>`);
the Lever company name is the one in `jobs.lever.co/<company>`.

### What each source gives

Fields a source does not publish stay empty (shown as "Not stated"); nothing is invented.

| Field | Career page (JobPosting) | Greenhouse | Lever |
|---|---|---|---|
| Title, location | Yes | Yes | Yes |
| Company | `hiringOrganization` | `company_name` | **No**: postings do not name the company |
| Description | Yes | Yes (HTML, cleaned to text) | Yes, with its sections ("Requirements", "Nice to have", …) |
| Job type | `employmentType` | A custom "Employment Type" field, if the board has one | `categories.commitment` |
| Salary | `baseSalary` | **No** | `salaryRange`, if published |
| Posted date | `datePosted` | `first_published`, else `updated_at` | `createdAt` |
| Remote | `jobLocationType: TELECOMMUTE` or "remote" in the location | "Remote" in the location | `workplaceType: remote` |
| Minimum experience | `experienceRequirements`, else the description | From the description ("3+ years of experience") | From the description |
| Required / nice-to-have skills | `skills`, else the description's headings | The description's headings | The description's sections |
| Original posting (`apply_url`) | `url` | `absolute_url` | `hostedUrl` |

Every job keeps its original posting (`apply_url`, also its de-duplication key), the page or API
response it was read from (`source_url`) and the extractor (`source`). A posting found again updates
the same row instead of creating a duplicate.

## Real and demo listings

- A job is **real** only if its `source` is a real-source extractor (`generic`, `greenhouse`, `lever`).
- The demo sites' jobs are **demo**: invented jobs, never real openings. So is a job from any source no
  extractor claims (for example one that was removed later).
- The crawler takes jobs from a demo site's host (`mock-site`, `realpython.github.io`) **only** through
  that site's demo extractor. Jobs another extractor finds there are dropped with a warning, and a crawl
  request that forces a real-source extractor onto a demo host is refused (422). A demo job can therefore
  never be saved as a real one.
- The API returns `listing: "real" | "demo"` with every job, `GET /jobs?listing=real` filters by it, and
  exports carry a `listing` column. The UI marks demo listings with a "Demo" badge and says on the job
  page that the job is invented.
- Real and demo jobs are matched by the same engine with the same formula and rules.

## Industries

Every job gets one of: Software & IT, AI & Data Science, Finance & Banking, Marketing, Sales & Business,
Human Resources, Design, Operations & Supply Chain, Healthcare, Education, Engineering, Legal, or
Other / Unclassified. The rules (`backend/app/industries/industries.json`) weigh the title (3 points per
term), the job's skills (1 point per skill of the industry) and the description (1 point per term). The
industry with at least 3 points and a clear lead wins; a weak or tied signal stays Other / Unclassified.
The job page lists the evidence ("Title: "nurse" (+3)"). Industries help people browse and filter; they
never change a match score.

The skill taxonomy covers non-IT work too (finance, marketing, sales, HR, design, operations,
healthcare, education, engineering and legal skills), so non-IT jobs and candidates have skills to match.

## Starting a crawl

In the UI: Background jobs → **New crawl** → choose a source. A job board needs only its board token or
company name; a career page or another site needs a seed URL and limits. With the API:

```bash
# A Greenhouse board (one request)
curl -X POST http://localhost:8000/background-jobs/crawl -H "Content-Type: application/json" \
  -d '{"seed_url": "https://boards-api.greenhouse.io/v1/boards/<board token>/jobs?content=true", "max_depth": 1, "max_pages": 1}'

# A company career page with JobPosting data
curl -X POST http://localhost:8000/background-jobs/crawl -H "Content-Type: application/json" \
  -d '{"seed_url": "https://careers.example.com/jobs", "max_depth": 2, "max_pages": 50}'
```

The crawler picks each page's extractor from its address, so `extractor` can stay empty.

## Rules every crawl follows

- **Only sites you may crawl.** Check a site's terms before crawling it. FITSCAN never logs in, never
  gets past paywalls, CAPTCHAs, anti-bot protection or any other access control, and identifies itself
  with `CRAWLER_USER_AGENT`.
- **robots.txt** is read for every host and obeyed, including `Crawl-delay`. On 22 November 2026,
  `boards-api.greenhouse.io` disallowed only `/embed/`, and `api.lever.co` allowed everything with a
  crawl delay of 1 second; the crawler checks again on every crawl, so a change there is respected.
- **Allow-list and private addresses.** A crawl stays on its allowed hosts (default: the seed's host);
  private, loopback, link-local and reserved addresses are refused (except `mock-site`, via
  `CRAWLER_PRIVATE_HOST_ALLOWLIST`).
- **Polite and bounded.** One request at a time per host with `CRAWLER_DEFAULT_DELAY_SECONDS` between
  requests, retries with backoff, `max_depth` and `max_pages`, and pages larger than 5 MB are refused.
- **HTTP first.** Headless Chromium is used only by extractors whose pages need JavaScript (today only
  the mock site's dynamic page).

## Limitations

- **Not supported:** LinkedIn, Indeed, Naukri, Glassdoor and similar aggregators. They need a login,
  block automated access or forbid crawling in their terms.
- **Career pages without JobPosting data** (or that build their list with JavaScript and publish no
  structured data) give no jobs through `generic`; such a site needs its own extractor.
- **Lever** postings do not name the company. Greenhouse publishes no salary fields.
- **One response per board.** FITSCAN reads the first API response. Greenhouse lists every open job in
  it; Lever also offers paging (`skip`, `limit`), which FITSCAN does not use, so a very large Lever board
  may need it.
- **Industries** come from rules, not a trained model: an unusual title can land in Other / Unclassified.

## Resumes

Resumes are PDFs uploaded by the user. The tests and demos use synthetic resumes made by
`backend/tests/resume_pdfs.py` (invented people, one- and two-column layouts, a skills table and a
scanned page). No real resume is stored in the repository; uploaded files stay in the `uploads` volume.

## Adding a source

1. Save a response from the site as a fixture: `backend/tests/fixtures/html/` or `json/`. Use invented
   data, or a page whose terms allow it.
2. Add `backend/app/extractors/<site>.py` with a `BaseExtractor` subclass: `name`, `label`,
   `description`, `domains`, `formats` (`("html",)` or `("json",)`), optionally `seed_template` and
   `seed_key_label`, and `parse(url, body)` returning `RawJob`s and links. Set `demo = True` only for a
   demo site with invented jobs.
3. Add tests that parse the fixture (fields, missing fields, skipped records) and, if needed, a crawl
   through the API against `httpx.MockTransport`.

The registry finds the file by itself; nothing else changes. The source then appears in `GET /sources`,
the crawl dialog and the Jobs page's source filter.

## Offline tests

No test touches the internet: pages and API responses come from saved fixtures through
`httpx.MockTransport`, and DNS is faked. The real-source fixtures describe invented companies in each
source's real response format: `tests/fixtures/json/greenhouse_jobs.json` (finance, healthcare,
engineering and IT jobs), `tests/fixtures/json/lever_postings.json` (marketing, sales, operations, legal
and design) and `tests/fixtures/html/careers_jsonld_academy.html` (education, HR and data). Run
`cd backend && pytest` (see the README's "Tests" for the database tests).
