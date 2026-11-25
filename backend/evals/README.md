# Evals

Run everything (inside the api container, against the running app):

```bash
make eval
```

Run only the fast unit-level checks on your machine (needs Python 3.12 and `pip install -r requirements.txt`):

```bash
cd backend && pytest -q -m "not stack"
```

## What is here

| File | Checks |
|---|---|
| `test_auction_rules.py` | SECI e-RA rules against the RfS's own worked examples (§40.2 scenarios 1 and 2, §41.3) plus edge cases |
| `test_excel_engine.py` | every formula matches Excel's saved values, KPIs, goal seek for IRR and DSCR, overrides are non-destructive, speed budget |
| `test_readers.py` | workbook structure, tender pages and 24 golden facts (quote must be on the cited page), history cleaning |
| `test_unseen_workbooks.py` | a generated wind model the app has never seen: different layout, no named ranges, no cached values, Python ground truth |
| `test_stack.py` | black-box over HTTP, like an external grader: health, self test, upload, async runs, bad input |
| `test_targets.py` | behaviour that must exist but is not built yet (xfail). These flip to XPASS as agents land; then remove the marker |

## Golden files

`expected/*.json` hold the answers: bid model KPIs and breakevens, the auditor's target findings,
tender facts with clause, PDF page and quote, and history cleaning results. Change a golden only
when you are sure the old value was wrong, and say why in the commit.

## Adding an unseen workbook

Add a generator to `fixtures/make_workbooks.py` that writes the .xlsx and returns the answers
computed in plain Python, then a test that compares. Ideas: merged multi-row headers, tariffs in
paise, INDEX/MATCH scenario tables, a Solar+ESS augmentation spike, an injected hardcode.
