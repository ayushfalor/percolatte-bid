# Solution

The single source of truth for what we are building. Phases implement this document; if the design
changes, change it here first and log why in `decisions.md`.

## In one paragraph

The bid manager uploads their own Excel bid model next to the tender PDF and past auction results.
Six agents read everything, check the model against itself and against the tender, imagine how
rivals will bid, and play the auction thousands of times under the exact RfS rules. The output is
a price ladder (chance of winning and profit at every tariff) and three numbers to act on: the
sealed entry bid, the target range and the walk-away floor. Every number links to its source: a
cell in their workbook, a page and quote in the RfS, or a written assumption.

## What the bid manager gets

1. **Three numbers**: entry bid (envelope 2), target range, walk-away floor, each with win chance and return.
2. **The bridge** from "model as received" to the recommended floor, step by step, each step clickable.
3. **The price ladder**: win chance and profit at every paisa from INR 2.00 to 2.80.
4. **What's wrong in the model**, priced in paise, with one-click fixes that never edit their file.
5. **What the tender says**, with page and quote, and where the model disagrees with it.
6. **Who the rivals are and why we think what we think**, frozen per scenario.
7. **A replay of a simulated auction** for the war room.

## Architecture

```
browser -> web (nginx + React) -> api (FastAPI) -> db (Postgres 16)
                                                     ^
                                  worker (agents) ---+  polls the runs table
```

- **Three working tables plus `settings`** (the key pasted on the Setup screen, D-012). `documents` (files, bytes in the row), `runs` (every agent run: queue, progress,
  audit log; write-once), `scenarios` (named what-ifs). Agent outputs are JSONB.
- **Async.** The API queues a run; the worker claims it with `FOR UPDATE SKIP LOCKED`, reports
  progress and stores the result. Scale with `--scale worker=3`.
- **Offline mode.** No API key: deterministic parts work fully; LLM parts replay cached results for
  the bundled sample files (cache keyed by file hash).
- **Contracts** live in `backend/app/core/contracts.py`. Each phase fills a module behind them.

## The six agents

| Agent | Job | Built with | Output | Phase |
|---|---|---|---|---|
| Reader | Workbook structure and reference graph; tender pages; history cleaning | Code (LLM only for tender facts) | Workspace facts | 0 to 2 |
| Auditor | Model bugs and tender-vs-model mismatches, each priced in INR/kWh with a fix-as-scenario; tornado | Code; LLM only to word findings | Findings, corrected breakeven | 1 |
| Scout | Facts about real rivals from the web, each with URL and date | LLM + web search; dated cache for offline | Dossiers (no probabilities) | 3 |
| Rival model | Per rival: chance to show up, MW, opening bid, lowest price, and why | Code calibrated on history; small LLM adjustments that must cite a fact | Frozen snapshot per regime | 3 |
| Engine | Profit curve from the workbook; Monte Carlo win odds; ladder; recommendation; replay | Code only | Ladder, recommendation, replay | 0, 4 |
| Copilot | What-ifs and explanations in chat | LLM with tools; every number must come from a tool | Answer + saved scenario | 5 |

No LLM orchestrator: the pipeline is plain code with versions.

### Fixes never edit the file

A finding's fix is a set of value overrides plus formula patches, applied to a copy of the workbook
in a temp directory and recalculated by our engine (D-010). Overrides alone are not enough: wiring
insurance means adding a term to every cell of the O&M row, because the model has no insurance cell
to override, and restoring a typed-over cell means putting the row's formula back rather than
typing today's answer into it. So a patch is either an **append**, whose template contains
`{current}` and expands to whatever the cell holds now, or a **replace**, which is a complete
formula rebuilt from the row's pattern. The uploaded file is never opened for writing.

`corrected_breakeven` applies every fix that is certain from the model or the tender, and excludes
any fix whose impact rests on an assumed number (D-011). On the sample that is the year-6 O&M
formula, insurance at 0.25% of capex and 8,766 hours, giving INR 2.6465 against INR 2.6039 as
received. The ALMM module re-price is worth about 37 paise more but rests on A-03, so it stays a
lever on the War Room rather than part of this number.

## The main engine

### Profit side (no randomness)
Run the user's workbook through our formula engine across tariffs (every 5 paise, interpolate,
recompute exactly at the recommended prices). For each tariff: equity IRR, minimum DSCR and equity
value above the hurdle. With "apply fixes" on, the Auditor's fixes are applied as overrides and formula patches on a copy (D-010).

### Win side (Monte Carlo)
1. **Rival draws.** The frozen snapshot holds about 5,000 joint draws of the whole field: who shows
   up, MW, opening bid and lowest acceptable price per rival, one shared "market shift" per draw so
   rivals move together, and sometimes a surprise aggressive bidder.
2. **Play the auction** for each draw and each of our candidate prices, using `core/auction_rules.py`
   for every rule: SE, H1 knockout on sealed bids, zones, L1 + 2% band, bucket filling, 50 MW minimum,
   partial-award rules, ties.
3. **Count**: P(win anything), P(win all 200 MW), expected MW, P(we are knocked out as H1).

Two modes, built in this order:
- **Ladder mode (fast):** "if we end at price p, do we win?" Rivals end at the lowest price they
  need to stay in the winning zone, never below their floor. Used for the ladder.
- **Replay mode (tick by tick):** 1 paisa cuts, timestamps, 30 minutes plus 8-minute extensions on
  zone changes. Used for the war-room replay and as a cross-check on ladder mode.

Same draws for every price and every scenario (common random numbers) and a fixed seed, so
differences come from inputs, not luck.

### The three numbers
- **Walk-away floor** = the stricter of the 14% IRR tariff and the 1.20x DSCR tariff.
- **Target range** = prices above the floor where P(win) x profit is highest.
- **Entry bid** = floor plus room for the typical 8 paise cut, with P(H1 knockout) at most 5%.

### What reruns when
- Cost what-ifs (interest, capex, CUF, module price, fixes): profit side only, seconds. Win odds do
  not move, because rivals do not see our costs. The UI says so.
- Our MW, the rules, or a different rival snapshot: rerun the Monte Carlo (background job).

## Rival snapshots

- **Regimes, each its own frozen snapshot**: `history` (rivals bid like the last 13 solar auctions),
  `almm_40` (they pass on 40% of the imported-panel saving), `almm_100` (all of it). The UI switch
  picks a snapshot; it never edits one.
- **The shift is derived, not guessed**: each INR 1/Wp of module price is worth about INR 0.08/kWh
  of tariff in our model; INR 14.5 to 10/Wp is about 37 paise; multiply by the regime's pass-through.
- **Behavior types from history**: leaders (won most, finished at L1), mid-pack, laggards (never
  won), and a wildcard (one-off very low bid, like INR 2.36 in MOCK-2026-036).
- **Real names** (ReNew, Adani Green, JSW Neo...) come from Scout and map visibly to a type, with an
  "assumed" badge and a toggle to anonymize.
- **Smaller field** than vanilla tenders: SEZ/EOU status and a connectivity grant are required.

### The live auction (D-013)

On the day the portal shows our price, our rank, the lowest price and the clock; nothing else. The Live
Auction screen takes those lines by typing and treats each as a constraint on the frozen rival draws: a
named rival is in and ends at or under its last bid, an L1 line means some rival ends at or under it, rank
r means r-1 rivals end under us. The simulated auctions that agree are priced with the same settlement
rules as the ladder, and the advice reads off that: hold while in the band with time left, cut to the
best price inside the band when outside it or in the last eight minutes, walk away when the band sits
under the walk-away or nothing above it wins. Under 200 surviving auctions the draws are bent instead
(floors capped at the bids) and the screen says so. The snapshot is never written.

## Rules we rely on (corrected)

See `docs/problem/03-domain-primer.md`. Key corrections: band for L1 INR 2.36 is INR 2.40; the
80% rule and the H1 knockout never happen together; the 80% rule bites below 875 MW of total bids;
price grid INR 2.00 to 2.80.

## UX (what matters is the flow, not the paint)

The test: in 3 seconds they know the three numbers and how sure we are; in 30 seconds, why; in 3
minutes they can verify any number.

1. **Setup**: agent timeline lights up live with time and cost per step.
2. **Bid Brief** (landing): three cards, the bridge, "depends most on" chips, must-dos (EMD INR 16 Cr, PBG INR 40 Cr, connectivity by Dec 2028).
3. **War Room** (hero): price ladder with hurdle line and zones, crosshair card, rival field, replay, what-if levers with ghost curves.
4. **Rivals**: one card per rival with distribution, reasons, sources, snapshot id.
5. **Audit and model X-ray**: findings by INR/kWh impact with fix toggles; driver graph; tornado.
6. **Tender**: clause cards with verified badges and quotes; reconciliation vs the model.
7. **Assumptions register**: every assumption with source type, value, impact rank, where used.
8. **Copilot drawer**: answers as before/after cards, "pin to War Room".

## Where the value comes from

- **Tender facts that move the price**: the ALMM exemption is worth about INR 70 lakh/MW of capex at a
  mock INR 10/Wp import quote (37 paise of tariff).
- **Clean data into pricing**: each paisa is about INR 1.3 lakh/MW of equity value.
- **Model problems priced**: insurance never wired is 4 paise (about INR 5.5 lakh/MW).
- **Things people cannot do well by hand**: check everything every time, join documents owned by
  different people, reason about win odds under the 2% band, hold the floor under pressure, remember.
- Time saved is real but small (about INR 1,000/MW per bid). Never the headline.

## Known limits

- Win odds are only as good as the rival assumptions; they are written down, frozen and stress-tested.
- The formula engine supports the common Excel functions; unsupported ones are reported, not guessed.
- Scanned PDFs need the OCR step (planned, not built).
- One block of capacity per bidder (no multi-project preference order).
