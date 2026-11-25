# Phase 2: Tender intelligence

Status: not started

## Goal

Pull every commercially binding fact from the RfS with clause, page and a quote that code has verified on the page; flag the unusual clauses; work offline.

## Scope

- `app/core/tender_extract.py`: `extract_facts`, `unusual_clauses`
- One LLM pass over the binding core (bid information sheet, Sections 1 to 6, Annexure-B) with a typed schema; a second pass for unusual clauses
- Quote check with `quote_on_page`; unverified facts shown in amber
- Cache by file hash in `data/cache/`; offline mode reads it
- Token and cost logging per run (`runs.cost_usd`)
- Auditor uses real tender facts for model-vs-tender checks

## Gate

`backend/evals/test_phase2_tender.py` must pass, plus everything from earlier phases.

## Start prompt for Claude Code

Run `/phase-start 2`, then:

> Build tender extraction. Use the golden facts in evals/expected/tender_facts.json as the target. Commit the cached extraction for the sample tender so offline mode passes.

## Gaps found when the previous phase closed

(filled by `/phase-close 1`)

<!-- The sections below are filled by /phase-close; the docs check requires them once the phase is closed. -->
