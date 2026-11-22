# Demo video: script and shot list (7 minutes at most)

Everything shown below exists and was verified on 22 November 2026. Before recording: `docker compose up -d`, wait until
`docker compose ps` shows every service healthy, and open http://localhost:5173. Use only synthetic resumes
(`cd backend && python -m tests.resume_pdfs sample-resumes` writes them to `backend/sample-resumes/`).

| Time | Shot | What to show | What to say |
|---|---|---|---|
| 0:00–0:25 | Landing page | Scroll the hero and the product sections; click **Get started**. | "FITSCAN collects job openings by crawling, reads resumes from PDFs, and matches each candidate to the best jobs, with explanations." |
| 0:25–0:55 | Dashboard | Totals (jobs split into real and demo), background jobs by status, system status. | "Everything runs as background jobs in a Celery worker; PostgreSQL stores jobs, candidates, matches and every log line." |
| 0:55–1:50 | Crawl: static and dynamic | Background jobs → **New crawl** → *Demo: FITSCAN mock site (static pages)* → start. Open the run: live progress and log lines, including the JavaScript page rendered in headless Chromium. | "HTTP by default; Playwright only for pages that need JavaScript. robots.txt, rate limits, retries and an SSRF guard apply to every crawl. These mock jobs are labelled demo." |
| 1:50–2:30 | Crawl: real job board | **New crawl** → *Greenhouse job board* → board name `codeforamerica` (or show the finished live run). Jobs page → **Real listings**: industry, source, **Original posting** link. | "Real sources: company career pages with JobPosting data, and the public Greenhouse and Lever APIs. Every real job links to its original posting; demo jobs can never be shown as real." |
| 2:30–3:35 | Resume upload | **Upload resumes**: a one-column, a two-column, a skills-table and a scanned resume, plus one encrypted PDF. Show the run log: OCR on the scanned file, a clear failure for the encrypted one. Open a candidate: skills, experience, education, "parsed with OCR". | "Each file is checked for size and the PDF signature, stored under a random ID, and parsed; scanned pages go through Tesseract. One bad file never stops the others." |
| 3:35–4:50 | Matching | Matching page: the formula. **Recompute matches**: keep 70/15/10/5 or change the weights (they must add up to 100). Open a candidate: top 10 jobs with score, matched and missing skills, explanation, score breakdown. | "Score = 70R + 15N + 10E + 5L: required skills, nice-to-have skills, experience and location. Text similarity only orders equal scores. Each run records its weights." |
| 4:50–5:30 | Job detail | A real job: Industry panel with its evidence, Source panel, top 10 candidates. | "The industry comes from explainable rules (title, skills and description) and never changes a score; weak evidence stays Other / Unclassified." |
| 5:30–6:10 | Search and exports | Jobs filters (skill alias "js", city spelling, real/demo, industry, source); Candidates filters; Exports page: CSV and JSON for jobs, candidates and the match table. | "Exports use the same filters as the tables, stream large files, and neutralise spreadsheet formulas." |
| 6:10–6:45 | Reliability | A failed or cancelled run with its reason; Matching page note that an older run never overwrites newer results; the GitHub Actions run. | "About a thousand automated tests run in CI against PostgreSQL with Tesseract; failures are recorded per item, and stale jobs are detected by heartbeats." |
| 6:45–7:00 | Close | README and DATA_SOURCES.md. | "Setup is one `docker compose up`. The data sources, their limits and how AI was used are documented in the repository." |

## Notes for an honest demo

- Automatic re-matching is **off** on the demo machine (`AUTO_REMATCH=false`): after a crawl, start the match run by
  hand and say so.
- Jobs collected after the last match run have no matches until the next recompute.
- Lever postings show "Company not stated", because Lever does not publish the company name.
- Do not show a personal resume: use the synthetic ones.
