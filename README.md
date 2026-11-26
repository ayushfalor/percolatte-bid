# Bid Workbench

![ci](https://github.com/ayushfalor/percolatte-bid/actions/workflows/ci.yml/badge.svg)

An agentic workbench for a solar developer's bid team, built on SECI's 700 MW C&I-1 tender
(RfS SECI/C&P/IPP/15/0009/26-27). It reads the bid model, the tender and auction history,
finds what is wrong, and prices the bid: win odds and profit at every tariff.

## Run it

You need Docker Desktop (Mac or Windows) or Docker Engine (Linux), running.

```bash
git clone https://github.com/ayushfalor/percolatte-bid.git
cd percolatte-bid
docker compose up --build
```

Open **http://localhost:3000**. The first build downloads Postgres and the Python packages, which
takes five to fifteen minutes depending on your connection; later starts take seconds. The three
sample files (bid model, tender PDF, auction history) load by themselves, the agents run by
themselves, and within a couple of minutes the Bid Brief shows the three numbers. Upload your own
bid model on the Setup screen and it is read, audited and priced the same way; the header lets you
switch between models.

This is built to run on your machine. Nothing is hosted anywhere; the optional server setup
further down is there if you ever want it, not something the evaluation needs.

No `.env` file and no API key are needed. Without a key the app runs in **offline mode**:
everything deterministic works fully and AI steps use cached results for the sample files.
To turn on live AI (the Copilot answers free-form questions, tender extraction gets a model pass):
`cp .env.example .env`, put the key you were given in `ANTHROPIC_API_KEY`, then `docker compose up -d`.
The key is never in the repo; `.env` is ignored.

Stop with `Ctrl+C` (or `docker compose down`). Wipe the database with `docker compose down -v`.

## Check it works

| Check | How |
|---|---|
| One-call self test | open http://localhost:8000/api/selftest, expect `"ok": true` |
| Full eval suite, inside the container | `make eval` or `docker compose run --rm -e API_URL=http://api:8000 api pytest -q` |
| Outside-in smoke test | `make smoke` or `bash scripts/smoke.sh` |
| Fast evals on your machine, no Docker | `make test` (needs Python 3.12; `make venv` sets one up) |
| PEP 8 and format check | `make lint` (the same two commands CI runs) |
| What is wrong with the bid model, priced in paise | `GET /api/workbooks/{id}/findings` |
| Which inputs move the breakeven most | `GET /api/workbooks/{id}/drivers` |
| The Bid Brief: three numbers, bridge, must-dos, from stored runs | `GET /api/brief/{id}` |
| Ask a what-if; a scenario and an engine rerun come back | `POST /api/chat {"message": "What if CUF is 30%?"}` |

## Try your own files

- In the UI: **Upload a file** (.xlsx, .xlsm or .pdf).
- From a terminal: `bash scripts/try-workbook.sh path/to/model.xlsx` prints what the app understood.
- API reference: http://localhost:8000/docs. The deterministic tools need no queue and no AI:

| Endpoint | What it does |
|---|---|
| `POST /api/documents` | upload a file (deduplicated by hash), queues the Reader |
| `GET /api/workbooks/{id}/structure` | sheets, named ranges, labelled inputs, unused numbers, legacy sheets |
| `GET /api/workbooks/{id}/parity` | recomputes every formula and compares with the values Excel saved |
| `POST /api/workbooks/{id}/evaluate` | recalculate with overrides, e.g. `{"overrides": {"Tariff": 2.5}, "outputs": ["Returns!C8"]}` |
| `POST /api/workbooks/{id}/goal-seek` | e.g. `{"variable": "Tariff", "target": "Returns!C8", "target_value": 0.14}` |
| `POST /api/auction/shortlist` | RfS §40.2: eligible capacity and H1 elimination from first-round bids |
| `POST /api/auction/allocate` | RfS §41: zones, L1 + 2% band and bucket filling from e-RA bids |
| `POST /api/runs`, `GET /api/runs/{id}` | queue an agent run, poll progress and result |

- Command line, no database needed:
  `docker compose run --rm api python -m app.cli goal-seek data/samples/bid_model.xlsx --variable Tariff --target 'Returns!C8' --value 0.14`

## How it is built

```
browser ──> web (nginx + React) ──> api (FastAPI) ──> db (Postgres 16)
                                                        ^
                                     worker (agents) ───┘   polls the runs table for jobs
```

**Agents** (one module each in `backend/app/agents/`):

| Agent | Job | Status |
|---|---|---|
| Reader | Excel, tender PDF and auction history into clean, cited facts | built (rule extraction, live LLM pass with a key, cache by file hash) |
| Auditor | Model bugs and tender-vs-model mismatches, each fix priced in INR/kWh | built (tender mismatches need Phase 2 facts) |
| Scout | Web research on rivals, facts with URL and date | planned |
| Rival model | Per rival: chance of bidding at each price, and why. Frozen once computed | built (calibrated on history, three regimes) |
| Engine | Win odds and profit at every price point, and how they move with inputs | built (price ladder, three numbers, replay) |
| Copilot | Chat: what-ifs become scenarios, the engine reruns | built (rule-based offline, every number grounded) |

**Database: three tables.** `documents` (files, bytes stored in the row), `runs` (every agent
execution: job queue, live progress and audit log; a finished run is never modified, which is what
makes a rival snapshot frozen), `scenarios` (named what-ifs). Agent outputs are JSONB, so no table per agent.

**Async:** the API writes a `queued` run; the worker claims it with `FOR UPDATE SKIP LOCKED`,
reports progress as it goes and stores the result. Scale workers with `docker compose up --scale worker=3`.

**Trust:** the formula engine recomputes the uploaded workbook and is checked against the values Excel
saved (551 of 551 match on the sample). Tender facts carry clause, page and a verbatim quote that is
checked against the page text.

## Data extraction flow

![Data extraction flow](docs/solution/data-extraction-flow.png)

Editable source: [docs/solution/data-extraction-flow.drawio](docs/solution/data-extraction-flow.drawio). Open it at
app.diagrams.net or with the Draw.io extension in VS Code. Dashed boxes are next to build.

## Evals

`backend/evals/` holds the suite we run on every push (see `backend/evals/README.md`):
RfS worked examples for the auction rules, engine parity and goal seek on the sample model,
reader golden files, a generated workbook the app has never seen (different layout, no named
ranges, no cached values, ground truth computed in Python), black-box HTTP tests, and
**targets**: behaviour written down before it is built (marked xfail until it passes).

The Auditor's gate also runs on a second generated workbook with the sample's two traps planted on
a different layout, and checks every priced finding by applying that finding's own fix and
measuring the breakeven, so a reported number cannot be a memorised constant.

## Configuration

All optional, set in `.env` (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | empty = offline mode |
| `WEB_PORT` / `API_PORT` | 3000 / 8000 | change if those ports are taken |
| `LLM_MODEL_SMART` / `LLM_MODEL_FAST` | claude-sonnet-5-5 / claude-haiku-4-5-20251001 | models for extraction, research, chat |
| `SEED_SAMPLES` | true | load the sample files on first start |
| `SIM_SEED` | 42 | Monte Carlo seed, so results are reproducible |

## Deploy it (optional)

Not needed to evaluate the app; it runs on your machine. If you ever want it on a server, one small VM with Docker is enough. Clone the repo to `/opt/bid-workbench`, put `POSTGRES_PASSWORD`
and optionally `DOMAIN` and `ANTHROPIC_API_KEY` in its `.env`, then:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Caddy serves HTTPS on `DOMAIN` (or plain HTTP without one), a nightly job dumps the database into
the `backups` volume and keeps 14 days, and every service restarts after a reboot. After that, a
version tag deploys from GitHub: `git tag v1.0.0 && git push origin v1.0.0` runs
`.github/workflows/deploy.yml`, which checks out the tag on the VM, restarts the stack, and runs
the smoke test and the deployed-app check against `DEPLOY_URL`. Secrets live in the VM's `.env`
and in GitHub secrets, never in the repo. Backups, restore and the VM steps are in
[docs/RUNBOOK.md](docs/RUNBOOK.md).

## Troubleshooting

See [docs/RUNBOOK.md](docs/RUNBOOK.md). Most common: a port is busy (set `WEB_PORT`/`API_PORT` in `.env`),
or Docker Desktop is not running.

## What we built and why, what we left out, where it breaks

**What we built.** A workbench that reads the developer's own bid model, the RfS and the auction
history, and gives the bid team three numbers they can defend: the entry bid, the target range and
the walk-away floor, with the chance of winning and the return at every paisa in between. Six
agents do the work: the Reader turns files into cited facts, the Auditor finds what is wrong in
the model and prices each problem in paise with a fix that never edits the file, the Rival model
turns the history into frozen beliefs about the field, the Engine plays the auction five thousand
times at every price under the RfS's own rules, and the Copilot answers what-ifs with numbers it
can trace to a tool. Everything deterministic runs with no API key, which is how a reviewer runs it.

**Why this way.** The dangerous errors in a reverse auction are the ones that make you look
cheaper, because those are the bids that win, so the Auditor comes before the auction. Every
number links to its source: a cell, a page and quote, or a row in the assumptions register. Rival
beliefs are frozen snapshots so a comparison stays fair. The rules of the auction live in one
module that the RfS's own worked examples test, and the Monte Carlo is proven to give the same
answers as that module. The evals were written before the code, on workbooks the app has never
seen, and they run on every push.

**What we left out.** The Scout (live web research on rivals) and dossiers; the smaller-field
adjustment for this tender's SEZ requirement (A-07); fix toggles on the Audit screen; the
"connectivity by a date" must-do, which no tender fact supports; OCR for scanned PDFs; and a
migration tool, since the three tables are created on start. It is not hosted anywhere: it is built
to run on the evaluator's own machine, and the server configuration is included but unused.

Where it breaks:
- Large models. A workbook of about 9,000 formulas takes around 25 s to load and 4.7 s per recalculation; the Auditor prices each fix with a goal seek, so an audit of that size can run for minutes. Not yet optimised.
- Functions the formula library lacks (OFFSET, INDIRECT on a built string) are reported by cell; numbers that depend on them are withheld, not guessed.
- Scanned PDFs need OCR, which is not built. Clause numbers on tender facts are best effort.
- The Scout (web research on rivals) is not built; rival names are the history's grouped labels.
- The Audit screen has no fix toggles: formula-patch fixes cannot be toggled as plain overrides, and the UI never computes totals itself.
- The economics curve does not carry equity value in crore yet, so expected value in crore needs a caller to supply npv_cr.
- The rival model is calibrated on 13 mock solar auctions. With real history the archetype and floor rules are the same, but the numbers would move.
- The tornado and the fix prices are first-order estimates from the local slope; only the corrected breakeven and the ladder's economics are solved exactly.

## LLM cost

In offline mode, which is the default and the mode reviewers run, the cost is zero: no call leaves
the machine. The Auditor, Rival model and Engine never call a model at all; their numbers come from the
formula engine, the rules module and the history. The Copilot understands what-ifs and the common
questions by rule with templated wording. With a key it also hands questions the rules cannot answer to
the model, with the stored run results as its only data, and every number in the reply still has to
pass the grounding check or the reply is withheld.

The one step that can call a model is tender extraction, and only when `ANTHROPIC_API_KEY` is set.
It makes one structured call over the RfS pages, verifies every quote by code, fills gaps from the
rule pass, and caches the result by file hash so the second run is free. Each run records an
approximate USD figure in `runs.cost_usd`, computed from the call's token counts at list price,
and the Reader's result carries the same number. On the sample tender the rule pass alone passes
every golden fact, so a key buys coverage on tenders the rules have not seen, not correctness on
this one.

## How this becomes a product a renewable developer would pay for

**The problem.** Every tender now has its own rules: peak-hour supply, round-the-clock supply,
batteries, special-zone buyers like this green hydrogen tender. Each comes with its own penalties,
grid deadlines and exceptions. A small bid team handling many tenders a year cannot check every
detail by hand, and one missed detail can lose the bid or cost 25 years of profit.

**Why not just Excel.** They keep Excel; we read it. Excel computes whatever is typed and never
says it is wrong. In a reverse auction the dangerous errors are the ones that make you look
cheaper, because those are the bids that win. Excel also gives return at a price, not the chance
of winning at that price.

**What they pay for.** Tender facts that move the price: in this tender, imported panels are
allowed, and at a mock quote that is INR 70 lakh/MW less capex and 37 paise lower breakeven. Win
odds under the real rules: the 2% band, the 80% rule, partial awards. Problems in their own model,
priced: here the missing insurance line is 4 paise. Discipline in the war room: the board's floor,
held, with instant answers. The unit of value is simple: one paisa on this 200 MW bid is about
INR 1.3 lakh per MW of equity value.

**Pricing.** A free model check (upload an old model, see its problems). A pilot at INR 3 lakh
for one live tender. Growth at INR 24 lakh a year for up to 12 tenders, about INR 1,000 per MW
per bid. Enterprise at INR 60 lakh to 1.2 Cr a year: self-hosted, unlimited, live war room. Setup
as a service on top.

**Honest ceiling.** Perhaps 40 to 80 groups bid regularly in India, by our estimate, so the bid
niche alone is a good business, not a big one. Growth comes from hybrid and FDRE tenders, lenders
and model auditors, C&I PPAs, and other reverse-auction markets.

## Documentation

- [docs/EXPLAINED.md](docs/EXPLAINED.md): the solution and the evals in simple English
- [docs/solution/SOLUTION.md](docs/solution/SOLUTION.md): the design; [decisions](docs/solution/decisions.md)
- [docs/problem/](docs/README.md): the brief, requirements traceability, domain primer, tender facts
- [ASSUMPTIONS.md](ASSUMPTIONS.md): every assumed number
