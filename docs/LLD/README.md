# Low-Level Design (LLD): Job–Candidate Matching Platform

**Version 1.1 · 18 November 2026 · Status: Planned design; all LLD decisions approved.** The repository contains no application code yet, so every part describes the intended implementation.

The High-Level Design says *what* the system's parts are and *why*. This LLD explains *how* each part works inside: modules, tables, endpoints, algorithms, error handling and tests. It is written in plain language for a developer who will build the system and for explaining it in an interview.

## Files

| File | Read it for |
|---|---|
| [01_Introduction_and_Architecture.md](01_Introduction_and_Architecture.md) | Purpose, implementation status and labels, platform overview, architecture diagram, technology stack, deployment services; **the register of approved LLD decisions (Section 1.6) and the HLD inconsistencies corrected in HLD v1.2 (Section 1.7)** |
| [02_Project_Structure.md](02_Project_Structure.md) | What exists today; the planned folders and files; what each module is responsible for; dependency rules |
| [03_Database_Design.md](03_Database_Design.md) | ER diagram; all eight tables with columns, types and keys; relationships; duplicate prevention; indexes |
| [04_Backend_and_API_Design.md](04_Backend_and_API_Design.md) | Backend layers; how a request is processed; API conventions and errors; every endpoint with JSON examples; exports |
| [05_Background_Jobs_and_Crawler.md](05_Background_Jobs_and_Crawler.md) | Celery and Redis; job lifecycle, progress, logs, cancellation and failures; the BFS crawler, URL rules, robots.txt, rate limits, retries and extractor plug-ins |
| [06_Resume_Parsing_and_Skill_Extraction.md](06_Resume_Parsing_and_Skill_Extraction.md) | PDF checks, two-column text, OCR, field extraction, validation; skill taxonomy and normalization; extraction quality checks |
| [07_Matching_Engine.md](07_Matching_Engine.md) | The scoring formula, edge cases, full-precision ranking with display-only rounding, explanations, tie-breaker, top-10 queries, worked example |
| [08_Frontend_Design.md](08_Frontend_Design.md) | React pages and components, the typed API client, polling for live progress, user workflows |
| [09_Error_Handling_and_Testing.md](09_Error_Handling_and_Testing.md) | How invalid input, failed PDFs, crawler errors and task failures are handled; unit, API and integration tests |
| [10_End_to_End_Workflows.md](10_End_to_End_Workflows.md) | The four complete flows (crawl, resumes, matching, viewing and exporting), step by step, with links to the details |
| [LLD_COMPLETE.md](LLD_COMPLETE.md) | All ten parts in one file, in order, for printing or reading start to finish |

## How to Read It

- **First time:** read Part 1, then Part 10 for the complete flows, then the parts you need.
- **To implement a component:** Part 2 (where the code goes), then the component's part (3–8), then Part 9 (its error cases and tests).
- **For an interview:** Parts 1, 5, 7 and 10 cover the architecture, background jobs, the crawler, matching and the end-to-end story.

## Conventions

- Section numbers start with the part number (Section 7.6 is in Part 7), so a reference such as "Section 5.8" can be found in any file.
- "HLD §8.5" refers to `docs/HLD_Job_Candidate_Matching_Platform_Full.md` (v1.2); "ADR-017" refers to `docs/ARCHITECTURE_DECISIONS.md`.
- Status labels (**Planned**, **Optional**, **Could**, **Open**, **LLD decision**, **Proposed name**) are defined in Part 1, Section 1.2.
- The LLD adds no features, endpoints, tables or columns beyond the HLD. Where the HLD left a detail open, the LLD makes a small choice labelled **LLD decision** (LLD-1 to LLD-11). All of them were approved on 18 November 2026 and are listed in Section 1.6. LLD-4 and LLD-6 to LLD-10 are also in HLD v1.2.
- Two inconsistencies found in HLD v1.1 were corrected in HLD v1.2 (Section 1.7). HLD v1.1 is kept in `docs/archive/v1.1/`.
- `LLD_COMPLETE.md` repeats the ten parts word for word. When a part changes, update `LLD_COMPLETE.md` as well.
