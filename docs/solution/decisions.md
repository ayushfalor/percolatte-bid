# Decision log

One entry per decision that someone could reasonably have made differently. Newest at the bottom.
Format: what we chose, why, what we gave up.

**D-001 Formula engine: the `formulas` Python library, gated by a parity check.**
Why: it evaluates IRR, INDEX and named ranges correctly on the sample (551 of 551 match Excel's
saved values), about 2 s to load and 0.15 s per recalculation. Gave up: a hand-written evaluator
would be faster but riskier on an unseen workbook. pycel broke on named ranges.

**D-002 Postgres is the job queue; three tables only.**
Why: one fewer service than Redis, and the runs table doubles as the audit log. Gave up: built-in
retries and scheduling of a queue library.

**D-003 File bytes live in the database.**
Why: api and worker are separate containers; no shared disk, no volume mistakes. Files are small.
Gave up: very large files (we cap uploads at 50 MB).

**D-004 Rival beliefs are frozen snapshots, one per regime.**
Why: the user's rule that rival output never changes once computed, and fair comparisons. A UI
switch selects a snapshot instead of editing one. Gave up: a free-form "aggressiveness" slider.

**D-005 Offline mode replays cached LLM outputs, keyed by file hash.**
Why: reviewers may run without an API key. Gave up: nothing for the sample files; new PDFs need a key.

**D-006 Monte Carlo in two modes: fast ladder first, tick-by-tick replay second.**
Why: the ladder needs thousands of auctions per price; the war room needs a believable minute-by-
minute story. Same rules module for both. Gave up: one unified simulator (slower or less faithful).

**D-007 Price grid INR 2.00 to 2.80, every paisa.**
Why: with imported panels the breakeven falls to about INR 2.28 (2.16 with the GST lever), below
the INR 2.25 to 2.65 range suggested earlier.

**D-008 Phases gated by `docs/phases/status.json`.**
Why: tests of unfinished phases are expected failures; closing a phase makes its tests mandatory in
CI forever after. Gave up: nothing; it is a single number in a file.

**D-009 Docs in the repo; raw notes private.**
Why: reviewers see distilled, checked documents. Raw call notes and AI chat exports go in `notes/`
(git-ignored).

**D-010 Fixes apply as formula patches on a temporary copy, not only as value overrides.**
Why: some fixes cannot be written as a value. Insurance (Inputs!C28) has no cell anywhere in the
model to override, so wiring it means adding a term to every cell of the O&M row. Restoring the
typed-over year-6 O&M cell means putting the row's formula back, not typing the number it happens
to produce today, which would go stale the moment an O&M input changed. So a fix carries two kinds
of patch. An **append** patch has `{current}` in its template, which expands to whatever the cell
holds now, formula or typed number; that is how insurance reaches all 25 years including the year
someone typed over. A **replace** patch is a complete formula, rebuilt from the row's own pattern
and translated to the target column. Patches are written to a copy of the workbook in a temp
directory and recalculated by our engine. The uploaded file is never opened for writing.
Order matters when fixes combine: every replace patch lands first, then every append patch
expands `{current}` against the result. Do it the other way round and restoring the year-6
formula silently drops the insurance that was just added to that cell.
Gave up: pure in-memory overrides. We now pay one workbook recompile per distinct patch set, so
compiled engines are cached by file hash plus the sorted patch set.

**D-011 `corrected_breakeven` applies only fixes that are certain, and excludes assumed numbers.**
Why: the number has to mean "what the model says once the things we are sure about are right".
Re-pricing modules at the mock INR 10/Wp (A-03) moves the breakeven by about 37 paise, which would
swamp everything else and bake an assumption into a headline figure. It stays a lever instead.
Gave up: a single number that includes the ALMM upside; the bridge on the Bid Brief shows it as its
own step.

**D-012 A fourth table, `settings`, for the key pasted on the Setup screen.**
Why: reviewers run with no `.env` and no terminal habit. The Setup screen takes a key, or the
passphrase that unlocks the demo key shipped encrypted in `deploy/env.enc`, checks it with one
tiny call, and keeps it in `settings`. Both the API and the worker read that row (the environment
still wins when set), so a tender uploaded later gets its model pass too. The row is a setting,
not an agent result, so write-once runs are untouched. Gave up: keeping the schema at three tables;
an environment-only key, which needed a terminal step evaluators kept tripping on.

**D-013 The live auction conditions the frozen rival draws by rejection, never by editing them.**
Why: on the day, the portal shows our price, our rank, the lowest price and the clock, and market
talk sometimes adds who is where. Each typed line is a constraint: a named rival is in and ends at
or under its last bid; an L1 line means some rival ends at or under it; rank r means r-1 rivals end
under us. The 5,000 simulated auctions are filtered to the ones that agree, and the same settlement
rules as the War Room price every tariff over the survivors. Fewer than 200 survivors means the
field is cutting below anything in its record; then every draw is bent instead (the rival's floor
capped at its bid) and the screen says so. The snapshot is never written; the same board gives the
same answer. Gave up: a live feed from the portal (it has none) and a Bayesian update of the
profiles themselves, which would have made the Rivals screen disagree with the Live screen.
