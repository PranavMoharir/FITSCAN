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

## Live verification (22 November 2026)

Two public boards were crawled once each into the running stack, after a database backup, with one API request per board:

| Source | Seed URL | Result |
|---|---|---|
| Greenhouse: Code for America | `https://boards-api.greenhouse.io/v1/boards/codeforamerica/jobs?content=true` | 10 of 10 jobs saved, company "Code for America", every job linked to its `job-boards.greenhouse.io` posting |
| Lever: Spotify | `https://api.lever.co/v0/postings/spotify?mode=json&limit=10` | 10 jobs saved (capped with `limit=10`), every job linked to its `jobs.lever.co` posting; company empty, as Lever does not publish it |

Both hosts' robots.txt allowed the requests. All 20 jobs are labelled real and the 108 earlier jobs (100 from Fake Python Jobs, 8 from the mock site) stay demo. The 20 got industries such as Software & IT, AI & Data Science, Marketing, Sales & Business and Finance & Banking; a few ("Engineering Manager", "Program Director") stay Other / Unclassified because the evidence is weak or tied. With `AUTO_REMATCH=false`, each crawl's log says no match run was queued; the new jobs get matches at the next manual recompute.

## Why these sources, and how they were checked

### Why these sources

- **Greenhouse and Lever job boards.** Many companies publish their openings through these two hiring systems,
  and each offers a public JSON API for job boards that needs no login or key. One request returns a board's open
  jobs with title, location, description and a link to the original posting, so a crawl is a single request and
  nothing has to be scraped from rendered pages.
- **Company career pages.** Many employers add schema.org `JobPosting` data to their own career pages so that
  search engines can list the jobs. One generic extractor reads that data from any such page, so an employer's
  own site can be crawled without writing a new extractor.
- **Demo sources (Fake Python Jobs and the mock site).** The brief suggests Fake Python Jobs as a starting point,
  and the site was made for practising scraping. The mock site runs inside Docker Compose and covers what a real
  site might not: a page that needs JavaScript (rendered with headless Chromium), a robots.txt with a disallowed
  path, and pages that never change, so demos and tests are repeatable and need no internet. Their jobs are
  invented and always labelled demo.

### How robots.txt was checked

robots.txt is not checked by hand. Before the first page of every crawl, the crawler reads the host's robots.txt,
then obeys it (`Disallow` and `Crawl-delay`) and writes the result to the crawl's log. The stored crawl logs show:

| Host | Crawls | robots.txt result |
|---|---|---|
| `mock-site:8080` | 14 (18–19 November) | Loaded every time; `/private/internal.html` (under `Disallow: /private/`) was skipped as "disallowed by robots.txt" in 12 crawls and never fetched |
| `realpython.github.io` | 2 (18 and 19 November) | Loaded; no page refused |
| `boards-api.greenhouse.io` | 1 (22 November) | Loaded; no page refused (that day the file disallowed only `/embed/`; see the rules below) |
| `api.lever.co` | 1 (22 November) | Loaded, with a crawl delay of 1 second; no page refused |
| `www.shopify.com` | 1 (22 November) | Loaded; no page refused |

### What was tested live, and what only offline

| Source | Live crawls (from the stored crawl logs) | Jobs in the database | Offline tests (saved files) |
|---|---|---|---|
| Fake Python Jobs | 18 November (6 pages) and 19 November (101 pages: the listing and every job page) | 100, demo | Listing and job pages |
| Mock site | 14 crawls of its static and JavaScript pages, 18–19 November, inside Docker | 8, demo (5 static, 3 JavaScript) | Static pages, the JavaScript page before and after rendering, robots.txt |
| Greenhouse | Code for America board, 22 November, 1 request | 10, real | A board response with invented companies |
| Lever | Spotify board with `limit=10`, 22 November, 1 request | 10, real | A postings response with invented companies |
| Company career page (`generic`) | `https://www.shopify.com/careers`, 22 November: 10 pages fetched, **no job extracted** | 0 | A career page with invented `JobPosting` data |

So the `generic` extractor has read jobs only from the saved test page. In the one live attempt, the pages fetched
included two job pages, but no job was extracted from any page, and the log does not say why. That crawl also left
the careers section (it fetched catalog, news and editions pages), because a crawl's allowed domain is a whole host.
Sources FITSCAN does not support, and its other limits, are listed under [Limitations](#limitations).

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
- **Career pages are verified only offline.** `generic` has not collected a real job yet: the only live attempt
  (Shopify careers, 22 November 2026) fetched 10 pages and extracted no job.
- **Allowed domains are whole hosts.** A crawl seeded at a careers page can follow links to other pages of the
  same host and use up `max_pages` there, as the Shopify crawl did. Keep `max_pages` small, or seed a host that
  serves only jobs (such as a job-board API).
- **Lever** postings do not name the company. Greenhouse publishes no salary fields.
- **One response per board.** FITSCAN reads the first API response. Greenhouse lists every open job in
  it; Lever also offers paging (`skip`, `limit`), which FITSCAN does not use, so a very large Lever board
  may need it.
- **Industries** come from rules, not a trained model: an unusual title can land in Other / Unclassified.

## Resumes

Resumes are PDFs uploaded by the user. The tests and demos use synthetic resumes made by
`backend/tests/resume_pdfs.py` (invented people, one- and two-column layouts, a skills table and a
scanned page). No real resume is stored in the repository; uploaded files stay in the `uploads` volume.

Synthetic resumes were chosen so that the tests, the demos and [`samples/`](samples/) hold no personal data and
cover the layouts the brief asks for. Resumes uploaded to a running FITSCAN stay in its `uploads` volume and
database; none is in the repository or in `samples/`.

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
