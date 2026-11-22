# AI usage

How AI tools were used to build FITSCAN, what the developer decided and checked, and where the limits are.

## Tool

FITSCAN was built with **Claude Code** (Anthropic's AI coding assistant, running Claude models) in the developer's
editor and terminal. No AI service is used **by** the application at run time: matching is a weighted formula, with
TF-IDF (scikit-learn) only to order equal scores, and industries come from explainable rules.

## How the work was organised

The project was built in phases (setup, database, crawler, resume parsing, matching, search and exports, landing
page, application UI, optional features, real job sources, final integration). Each phase followed the same loop:

1. **The developer set the scope and constraints**: what to build, what not to touch, and safety rules (no real
   crawls, uploads or full recomputations without approval; never reset the database; no commits without approval).
2. **The assistant audited the code and proposed a plan**; the developer approved or changed it. Design decisions
   were the developer's: for example the scoring formula and its edge-case rule for jobs without skills, adjustable
   weights as whole numbers that must add up to 100, automatic re-matching with an off switch (`AUTO_REMATCH`), the
   brand palette and page design, and which optional features to build or defer.
3. **The assistant implemented** code, tests and documentation, ran the tests, and reported results, including
   failures and anything skipped.
4. **The developer reviewed** the report and the diff, then approved the commit and the push.

Commits written this way carry a `Co-Authored-By: Claude` line.

## What the assistant did

- Drafted the HLD, LLD and architecture decisions from the brief, then the code that implements them.
- Wrote the backend (FastAPI, SQLAlchemy, Alembic, Celery), the crawler and extractors, resume parsing with OCR, the
  matching engine, the frontend (React, Tailwind CSS, shadcn/ui), Docker Compose and the CI workflow.
- Wrote the automated tests and the offline fixtures (invented companies and people), and ran browser checks against
  a contract mock of the API and read-only checks against the running application.

## How the output was checked

- **Automated tests**: over a thousand backend tests (unit and PostgreSQL integration, run against a separate
  `matching_test` database), the TypeScript build, and GitHub Actions on every push.
- **Mutation checks** for safety rules: deliberately broken copies of the code (for example without the match-queue
  lock or without the demo-site guard) were run to confirm the tests catch the defect.
- **Live checks** against the running stack: read-only browser runs that block every write request, database
  snapshots before and after, a database backup before migrations, and two small approved live crawls (20 jobs).
- **Hand checks** recorded in the README (the top jobs of five candidates).

## Data and privacy

- Test data is synthetic: invented resumes (`backend/tests/resume_pdfs.py`) and invented companies in the job-board
  fixtures. No real resume is in the repository.
- Logs never contain resume text, names or contact details; uploaded files are stored under random IDs.
- The assistant worked on the developer's machine; secrets in `.env` were not printed or committed.

## Limits

- The developer is responsible for the final result. AI-written code and text were reviewed, but not every line was
  written by hand.
- Industry classification and skill extraction are rule-based: they are explainable and tested, not perfect.
- Live verification covered two job boards; other sources rely on the saved-fixture tests.
