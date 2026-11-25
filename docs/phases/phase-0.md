# Phase 0: Foundation

Status: done

## Goal

A repository anyone can run with one command, with the plumbing every later phase needs: a
database, a background worker, a formula engine that agrees with Excel, the RfS auction rules,
an eval suite with phase gates, CI on every push, and docs that explain it all.

## What we built

In plain English: the app starts with `docker compose up --build`, loads the three sample files,
reads them in the background, and can already recalculate the bid model and find the breakeven
tariff. The auction rules are written as code and checked against the tender's own examples.
Every later phase has its contract and its tests waiting.

Files:
- `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `Makefile`, `scripts/`
- `backend/app/models.py`: three tables (documents, runs, scenarios)
- `backend/app/worker.py`: queue on Postgres with `SKIP LOCKED`, live progress
- `backend/app/core/excel_engine.py`: evaluate, goal seek, parity with Excel
- `backend/app/core/workbook_reader.py`, `tender_reader.py`, `history_reader.py`: the Reader's deterministic parts
- `backend/app/core/auction_rules.py`: SE, H1 knockout, zones, L1 + 2% band, partial awards
- `backend/app/core/contracts.py` plus stubs for phases 1 to 5
- `backend/evals/`: golden files, unseen workbook generator, phase gates, docs check
- `.github/workflows/ci.yml`: fast job and Docker job on every push
- `CLAUDE.md`, `.claude/commands/`, `docs/`

## How to check it

- `docker compose up --build`, open http://localhost:3000: four green lights, three files, runs succeeding
- http://localhost:8000/api/selftest returns `"ok": true`
- `make eval` (full suite in Docker) and `make smoke`
- `docker compose run --rm api python -m app.cli goal-seek data/samples/bid_model.xlsx --variable Tariff --target 'Returns!C8' --value 0.14` prints about 2.6039

## Eval results

- Fast suite (no Docker): 62 passed, 1 skipped (needs a deployed URL), 54 expected failures (phases 1 to 6, not built yet).
- Stack suite over HTTP: 5 passed, 2 expected failures (Copilot, Phase 5).
- What the passing tests prove: every formula in the sample matches Excel's saved values (551 of 551);
  goal seek gives INR 2.6039 for 14% and INR 2.3757 for a 1.20x DSCR; the auction rules reproduce the
  RfS examples (clauses 40.2 and 41.3) plus edge cases (875 MW threshold, partial awards for 200 MW);
  a never-seen wind workbook recalculates to the Python answer; 24 tender facts sit on their cited
  pages; the history cleaning finds 1 duplicate, 1 paise tender and 20 bidder groups; the app runs
  over HTTP with bad inputs rejected cleanly.

## Decisions

D-001 to D-009 in `docs/solution/decisions.md`.

## Questions they may ask

**Q:** How do I run it, and what do I need installed?
**A:** Only Docker. `git clone`, then `docker compose up --build`, then open http://localhost:3000. No `.env` and no API key are needed; every setting has a default in `docker-compose.yml`.

**Q:** Why Postgres, and why only three tables?
**A:** `documents` holds the files, `runs` holds every agent run (it is the job queue, the progress feed and the audit log), `scenarios` holds what-ifs. Each agent's output has a different shape, so it is stored as JSONB in its run instead of in a table per agent. Fewer tables, fewer migrations, nothing lost.

**Q:** How is it asynchronous?
**A:** The API inserts a run with status `queued` and returns at once. The worker claims the oldest queued run with `SELECT ... FOR UPDATE SKIP LOCKED`, writes progress to the row as it goes, and stores the result. The UI polls the run. Several workers can run safely: `docker compose up --scale worker=3`.

**Q:** How do you know your numbers match Excel?
**A:** On upload we recompute every formula with our engine and compare with the values Excel saved in the file: 551 of 551 match on the sample (`test_engine_matches_every_excel_value`). For a workbook without saved values we test against answers computed separately in Python (`test_unseen_workbooks.py`).

**Q:** What happens with a workbook you have never seen?
**A:** Nothing in the product code names a sheet or a cell. Labels come from the text next to each number, roles come from the reference graph, and the API takes explicit cells if our guess is wrong. The eval suite generates a wind model with a different layout, no named ranges and no saved values, and checks recalculation and goal seek on it.

**Q:** What if I don't have an API key?
**A:** Offline mode. Everything deterministic works: reading, recalculating, goal seek, auction rules. AI steps (tender extraction, rival research, chat) will replay cached results for the bundled sample files once those phases land; a new PDF without a key shows a clear message instead of failing.

**Q:** How did you test the auction rules?
**A:** Against the RfS's own worked examples: the two shortlisting scenarios in clause 40.2 and the allocation example in 41.3, where our code picks exactly the same winners. Edge cases are tested too: a tie for highest bid, the 875 MW threshold where the 80% rule stops biting, and partial awards of 110, 80 and 40 MW on a 200 MW bid.

**Q:** What does CI do?
**A:** On every push and pull request: a fast job runs all evals without Docker in about two minutes, then a second job builds the whole app in Docker with no `.env` and no key, runs every eval inside the container against the live stack, and runs the smoke test. Green CI means it runs for a reviewer.

**Q:** What is not built yet?
**A:** The Auditor, LLM tender extraction, rivals, the Monte Carlo engine, the bid manager screens and the Copilot. Each has its contract in `backend/app/core/` and its gate tests in `backend/evals/test_phase*.py`, which are expected to fail until their phase closes.

**Q:** Why store the uploaded files inside the database?
**A:** The api and worker run in separate containers. Keeping the bytes in the `documents` row means neither needs a shared disk, uploads are de-duplicated by hash, and a backup of the database is a backup of everything. Uploads are capped at 50 MB.
