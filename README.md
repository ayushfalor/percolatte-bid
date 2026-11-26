# Bid Workbench

![ci](https://github.com/ayushfalor/percolatte-bid/actions/workflows/ci.yml/badge.svg)

An agentic workbench for a solar developer's bid team, built on SECI's 700 MW C&I-1 tender
(RfS SECI/C&P/IPP/15/0009/26-27). It reads the bid model, the tender and auction history,
finds what is wrong, and prices the bid: win odds and profit at every tariff.

## Run it

Five minutes of your attention, then it runs by itself. Nothing is hosted; it all runs on your machine.

**Step 1. Install Docker (once).** You need Docker Desktop on Mac or Windows, or Docker Engine with the
compose plugin on Linux. Open Docker Desktop and wait until it says the engine is running. Check from a
terminal: `docker compose version` prints a version number.

**Step 2. Get the code and start it.** In a terminal (Mac: Terminal; Windows: PowerShell, or a WSL
Ubuntu terminal if you have one; Linux: any shell):

```bash
git clone https://github.com/ayushfalor/percolatte-bid.git
cd percolatte-bid
docker compose up --build
```

No `.env` file, no API key, no other install. Leave that terminal open; it shows the logs.

**Step 3. Wait for the first build.** The first run downloads Postgres and the Python packages and builds
the UI: five to fifteen minutes depending on your connection. You will see lines like
`api-1 | Uvicorn running on http://0.0.0.0:8000` and `worker-1 | ...`. Later starts take seconds.

**Step 4. Open the app.** Go to **http://localhost:3000** in a browser. It opens on the Setup screen.
The three sample files (a bid model, the tender PDF, the auction history) are already loaded as the
sample project, and the four agents start by themselves. Watch the four ticks (Read, Audited, Rivals,
Priced) fill in; it takes one to three minutes.

**Step 5. Use it.** When the header says "Priced and ready":

1. **Bid Brief**: the three numbers (entry bid, target range, walk-away) and why.
2. **War Room**: win chance against return at every price. Pick an input, type a value, press
   "Price it" to see the numbers move.
3. **Live Auction**: on auction day, type in what the portal shows and get hold, cut or walk away.
4. **Setup, Upload a file**: drop in your own bid model (.xlsx); it is read, audited and priced the same
   way, and the Project picker in the header switches between models.
5. **Ask the Copilot** (top right): "What if CUF is 30%?", "Should we bid at 2.40?", "What is wrong
   with the model?"

**Live AI is optional.** Everything above works with no key. To turn it on, go to Setup, the "Live AI"
box, and paste either your own Anthropic key or the passphrase from the submission note. The
passphrase unlocks the demo key that ships encrypted in `deploy/env.enc`; the key is checked once and
kept only in the app's local database, which publishes no port. No terminal step. (The old way still
works: `make env PHRASE=<phrase>` writes `.env`, or `cp .env.example .env` and set
`ANTHROPIC_API_KEY`.) The plain key is never in the repo; `.env` is ignored.

**Stop and reset.** `Ctrl+C` in that terminal stops it; `docker compose down` from another terminal
does the same. `docker compose down -v` also wipes the database, so the next start is a fresh one.
To run it in the background instead: `docker compose up --build -d`, then `docker compose logs -f`
to watch, `docker compose down` to stop.

**If anything looks wrong**, the table under [Troubleshooting](#troubleshooting) covers every case
we have met.

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
| The live auction: type in the board, get the next move | `POST /api/live/{id} {"observations": [{"minute": 5, "bidder": "L1", "tariff": 2.41}], "our_price": 2.45, "minutes_left": 20}` |
| The tender in plain words, with what each unusual clause means | `GET /api/tender/plain` |

## Try your own files

- In the UI: **Upload a file** (.xlsx, .xlsm or .pdf). Any layout works, but a bid model must have a
  tariff input and an equity IRR result the app can find by their labels; Setup lists the labels under
  "What a bid model needs" and offers the sample model as a template to download. A file that does not
  fit is refused on the spot with a popup saying what is missing, and never reaches the agents.
- From a terminal: `bash scripts/try-workbook.sh path/to/model.xlsx` prints what the app understood.
- API reference: http://localhost:8000/docs. The deterministic tools need no queue and no AI:

| Endpoint | What it does |
|---|---|
| `POST /api/documents` | upload a file (deduplicated by hash), queues the Reader |
| `GET /api/template`, `GET /api/template/requirements` | the sample model as a template to download; what a model must contain |
| `GET /api/workbooks/{id}/structure` | sheets, named ranges, labelled inputs, unused numbers, legacy sheets |
| `GET /api/workbooks/{id}/parity` | recomputes every formula and compares with the values Excel saved |
| `POST /api/workbooks/{id}/evaluate` | recalculate with overrides, e.g. `{"overrides": {"Tariff": 2.5}, "outputs": ["Returns!C8"]}` |
| `POST /api/workbooks/{id}/goal-seek` | e.g. `{"variable": "Tariff", "target": "Returns!C8", "target_value": 0.14}` |
| `POST /api/auction/shortlist` | RfS §40.2: eligible capacity and H1 elimination from first-round bids |
| `POST /api/auction/allocate` | RfS §41: zones, L1 + 2% band and bucket filling from e-RA bids |
| `POST /api/runs`, `GET /api/runs/{id}` | queue an agent run, poll progress and result |
| `POST /api/scenarios`, `POST /api/scenarios/{id}/run` | save an input change and price it; the War Room shows the result |
| `GET/POST/DELETE /api/settings/llm` | live AI on or off: a key or the demo passphrase, checked before it is saved |

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

**Database: three working tables plus settings.** `documents` (files, bytes stored in the row), `runs`
(every agent execution: job queue, live progress and audit log; a finished run is never modified, which
is what makes a rival snapshot frozen), `scenarios` (named what-ifs), and `settings` (the key pasted on
the Setup screen, D-012). Agent outputs are JSONB, so no table per agent.

**Screens, in the order a new user meets them.** *Setup*: load files, watch four ticks, turn on live AI.
*Bid Brief*: the three numbers and why. *War Room*: win chance against return at every price; change any
input and price it. *Live Auction*: on the day, type in what the portal shows (our price, rank, the lowest
price, the clock, any rival you can place) and get hold, cut to a price, or walk away. *Audit*, *Tender*
(in plain words), *Rivals*. The header names the project: plant type read from the model's own labels,
tender, our MW, the file, and where it is in the pipeline.

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

| What you see | What it means | What to do |
|---|---|---|
| `docker: command not found` or `Cannot connect to the Docker daemon` | Docker is not installed, or Docker Desktop is not running | Install Docker Desktop, open it, wait for "Engine running", try again |
| `Bind for 0.0.0.0:3000 failed: port is already allocated` (or 8000) | Another program uses that port | Create a file named `.env` next to `docker-compose.yml` with `WEB_PORT=3001` (and/or `API_PORT=8001`), run `docker compose up --build` again, open http://localhost:3001 |
| The build stops with a network error while downloading | A flaky connection during the first build | Run `docker compose up --build` again; it continues from where it stopped |
| The browser says "This site can't be reached" | The build is still running, or the stack is down | Wait for `Uvicorn running` in the logs; or run `docker compose ps` and check `api`, `web`, `db`, `worker` are "running" |
| The page shows "Can't reach the app's API" | The web container is up but the API is not | `docker compose logs api` shows the error; `docker compose down -v` then `up --build` gives a clean start |
| The four ticks never fill in | The worker is not running, or a run failed | `docker compose logs worker`; on Setup open "Details for engineers" to see which run failed and its message |
| "Priced and ready" but the Brief shows n/a | The Engine ran before the rivals on an older database | On Setup press "Run again" |
| Live AI says "Anthropic rejected this key" | The key or passphrase is wrong or revoked | Check it is pasted whole; passphrases are case-sensitive; ask the sender for a fresh one |
| Everything is very slow on Windows | The repo lives under `C:\` and Docker goes through a file-system bridge | Clone inside WSL (for example `~/code`) and run from there |
| You changed code and nothing changed | The old image is running | `docker compose up --build` rebuilds what changed |

More detail, including backups and the optional server setup, in [docs/RUNBOOK.md](docs/RUNBOOK.md).

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

**What we left out, and why.** Everything below was a deliberate choice, not an oversight.

| What is missing | Why we left it out | What it means for you |
|---|---|---|
| **Web research on rivals** (the Scout agent) | It needs live web search and an API key, and the auction history already gives a solid, checkable picture of who bids and where they stop. The plan said to cut this first if time ran short, and it did. | Rivals are named by their history labels, not real company names, and there are no news-style dossiers. |
| **A "smaller field" adjustment** for this tender's special-zone requirement | We had no data to say *how much* smaller the field would be, and a made-up number would look like knowledge. | Win odds may be a little cautious: the model assumes the usual crowd shows up. |
| **Switching fixes on and off** on the Audit screen | Some fixes change formulas, not just numbers, so a simple toggle cannot apply them, and we never let the screen do its own arithmetic. | Use the bridge on the Bid Brief: it shows what each fix is worth, one line at a time. |
| **A "connectivity by date" must-do** | No clause in the tender gives that date. We would rather show four must-dos we can prove than five with one guessed. | Check the connectivity deadline against the RfS yourself. |
| **Reading scanned PDFs** | This tender has a proper text layer, and OCR would add a heavy dependency for a case we did not have. | A scanned tender will be read as empty pages and say so. |
| **A database migration tool** | There are four small tables, created automatically on start. A migration framework would be more machinery than the problem needs. | If the table layout changes, `make reset` rebuilds the database. |
| **A live feed from the auction portal** | SECI's portal has no data feed; it shows each bidder its own price, its rank, the lowest price and the clock. So the Live Auction screen takes those by typing, which is how a bid manager reads them off the portal anyway. | During the auction one person types the board as it moves; the advice updates within a second. |
| **A hosted version** | It is built to run on your own machine, which is how it is evaluated. The server setup is included and tested for shape, but nothing is deployed. | Run it locally; the optional deploy steps are there if you ever want them. |
| **A model writing the answers** when there is no key | Reviewers run without a key, so the Copilot understands what-ifs and the common questions by rule. With a key it uses a model only for questions the rules cannot answer, and still checks every number. | Without a key the Copilot is precise but literal; with one it is more conversational, never less honest. |

Where it breaks:
- Large models. A workbook of about 9,000 formulas takes around 25 s to load and 4.7 s per recalculation; the Auditor prices each fix with a goal seek, so an audit of that size can run for minutes. Not yet optimised.
- Functions the formula library lacks (OFFSET, INDIRECT on a built string) are reported by cell; numbers that depend on them are withheld, not guessed.
- Scanned PDFs need OCR, which is not built. Clause numbers on tender facts are best effort.
- The Scout (web research on rivals) is not built; rival names are the history's grouped labels.
- The Audit screen has no fix toggles: formula-patch fixes cannot be toggled as plain overrides, and the UI never computes totals itself.
- The economics curve does not carry equity value in crore yet, so expected value in crore needs a caller to supply npv_cr.
- The rival model is calibrated on 13 mock solar auctions. With real history the archetype and floor rules are the same, but the numbers would move.
- The tornado and the fix prices are first-order estimates from the local slope; only the corrected breakeven and the ladder's economics are solved exactly.

## What we would improve with more time, and why

Each line gives the change, the number that justifies it, and a rough effort. The numbers are this
repo's own measurements unless the line says otherwise.

| Improvement | Why, with the number | Rough effort |
|---|---|---|
| **Test every screen in a real browser, automatically** | The one bug that reached a user was a missing number in a stored run that blanked the page. All 249 automated tests were green, because none of them renders the UI. Mounting each screen against the running app in a headless browser takes about two seconds per screen (that check, run by hand, is how the bug was found) and would have caught it before the push. | 1 day |
| **Make large models fast** | A 9,000-formula model loads in 25 s and recalculates in 4.7 s. Pricing one fix is a goal seek of about 8 recalculations (8 x 4.7 s = 38 s), so ten fixes on a model that size take about 6 minutes. Caching the compiled model across runs and pricing fixes from one shared sensitivity curve would bring an audit under a minute. | 3 days |
| **More simulated auctions** | 5,000 draws put a 50% win chance within about ±1.4 points (sampling error, 95% band). 50,000 draws would make that ±0.4 points for about 1 s of compute instead of 0.1 s, still fast enough for the live screen to recompute on every typed bid. | Half a day |
| **Calibrate rivals on real results** | The rival model learns from 13 mock auctions, with 37 bidder names grouped into 16 rivals in this field; 1 of the 16 bid in two or fewer of those auctions, so its stopping price is the field's average, not its own, and the same would be true of any newcomer. SECI publishes every solar ISTS result; loading them would give each serious rival its own record. | 2 days, plus the data |
| **Build the Scout agent** | 0 of the 16 rivals has anything beyond its auction record. A web pass per rival (recent wins, module supply deals, financing news) adds the one thing history cannot show: who needs this win. | 3 days, needs a key |
| **Feed the live auction without typing** | The SECI portal has no data feed, so the Live Auction screen takes bids by typing, a few seconds each during the hour that matters most. A screen-capture reader of the auction window would make that zero seconds and remove typing slips. | 4 days |
| **Read tenders we have not seen, offline** | The 25 extraction rules were written against one RfS. On a new tender the model pass does the work and the rules fill gaps; without a key, only the rules run. Rules built across the last ten SECI and SJVN tenders would make offline reading as good as the model's. | 2 days per tender family |
| **A checker that knows every unit** | Every number the Copilot writes is checked against a tool output; a number the checker cannot match withholds the whole answer. In one hour of testing, three correct answers were withheld (paise, a negative sign, an ID like A-03) until the checker learned those forms. Each new form is a line, but the list is still growing. | 1 day |
| **Expected value in rupees** | The ladder's expected value is MW won times the margin over the floor, because the workbook's equity value is not wired through yet. With it, the target range would be stated in crore, which is what a board asks for. | 1 day |
| **A team, not a single screen** | One project list, no accounts, one database. A bid team of five needs its own scenarios per person and a lock on the one Brief that goes to the board. | 3 days |

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
