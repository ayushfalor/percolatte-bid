# Bid Workbench: instructions for Claude Code

## What this is
An agentic workbench for a solar developer's bid team on SECI's 700 MW C&I-1 tender. It reads the
bid model (Excel), the tender (PDF) and auction history, finds what is wrong, and prices the bid:
win chance and profit at every tariff. Graded on: robust Excel ingestion (they test an unseen
workbook), depth and correctness of the Excel agent, tender context carried into the auction
simulation, and a UI a non-technical bid manager can trust. They will run their own evals.

## Read first
- `docs/solution/SOLUTION.md`: the design. Change it before changing the design in code.
- `docs/phases/status.json`: which phase we are in. `PLAN.md` and `phase-N.md` are local only
  (git-ignored), along with `.claude/commands/`.
- `docs/problem/03-domain-primer.md`: domain words and RfS rules. Never invent tender facts.
- `ASSUMPTIONS.md`: every assumed number. Add a row when you assume something new.

## Commands
- `make up` / `make down` / `make reset` (wipes the DB) / `make logs` / `make ps`
- `make test`: fast evals on your machine, no Docker (`cd backend && pytest -q -m "not stack"`)
- `make lint`: ruff check and ruff format --check on the backend (CI runs the same two commands)
- `make eval`: full evals inside Docker against the running stack
- `make smoke`: outside-in smoke test

## Rules
1. Evals first. Confirm or write the failing eval before the code. Never weaken a test to pass it.
2. Never hardcode cell addresses or sheet names in product code. Tests may use the sample's cells.
3. Numbers shown to users come from code (formula engine, rules, simulation), never from LLM text.
4. Never modify an uploaded file. Fixes and what-ifs are overrides.
5. Finished runs are write-once. A rival snapshot never changes; new beliefs mean a new run.
6. Every rule of the auction goes through `backend/app/core/auction_rules.py`.
7. Offline mode must keep working (no API key): cache LLM outputs by file hash.
8. Keep three working tables plus `settings` (D-012). Agent outputs go in JSONB. A new table needs a decision log entry.
9. Fixed seeds for anything random. Same inputs, same outputs.
10. Pin dependencies; after editing `backend/requirements.txt`, run `make lock`.
11. Do not say a step is done until `make test` passes; a phase is not done until `make eval` passes
    and its doc is complete (`evals/test_docs.py`).

## Python standards (backend)
Style
- PEP 8 and PEP 257, enforced by ruff (lint and format). `make lint` must pass; CI runs it.
- Type hints on every function signature. Frozen dataclasses for data. pathlib, f-strings, logging (never print).
- Flat code: guard clauses and early returns. No nested ifs that can be one condition (write `if a and b:`), no long if/elif ladders where a dict lookup works, no else after return.
- Comprehensions, any(), all(), sum(), zip() and enumerate() instead of manual append loops and index arithmetic. Generators for large streams.
- Small functions (aim under 40 lines), one job each. Descriptive snake_case names, UPPER_CASE constants, no magic numbers in logic.
- Specific exceptions only (no bare except), no mutable default arguments, no dead or commented-out code, no TODO without a phase number.
Performance
- Measure first: every agent run records elapsed_ms; speed budgets live in the evals.
- Never recalculate the workbook inside a loop when a precomputed curve plus interpolation will do. Cache compiled engines.
- Number crunching (Monte Carlo, sweeps): vectorized NumPy, no per-draw Python loops where an array operation works.
- Dicts and sets for lookups, not repeated list scans. Read each workbook once per run and reuse the result.
- CPU-heavy work runs in the worker, never in an async API handler. Database: one session per request or job, no queries inside loops, select only the columns you need.

## Writing style for docs
Plain English, short sentences, no em dashes. Explain like the reader is smart but new to the domain.
Reviewer Q&A uses `**Q:**` and `**A:**`, answers in plain semi-technical English.

## Do not
- Commit `.env`, keys, or anything from `notes/`.
- Change files in `backend/evals/expected/` without saying why in the commit message.
- Add a service to docker-compose without updating README and RUNBOOK.
