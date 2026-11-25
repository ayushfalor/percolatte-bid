# Phase 1: Model understanding

Status: not started

## Goal

The Auditor reads any workbook and says what drives the result, what looks wrong, and what each problem is worth in paise, with fixes that never edit the file.

## Scope

- `app/core/audit.py`: `audit_workbook`, `corrected_breakeven`, `tornado`
- Checks (all template-free): typed-over formula rows, ranges shorter than their siblings, unused inputs, inputs that change nothing, stale notes, whole-number percents, legacy sheets, tender-vs-model mismatches (using the golden tender facts until Phase 2 lands)
- Each finding: severity, evidence, INR/kWh impact, fix as overrides
- Labels from row text and column headers (so Scenarios!D5 reads as CUF)
- Auditor agent wired into the worker; API endpoint for findings

## Gate

`backend/evals/test_phase1_auditor.py` must pass, plus everything from earlier phases.

## Start prompt for Claude Code

Run `/phase-start 1`, then:

> Implement the Auditor. Start with a failing run of evals/test_phase1_auditor.py, then add one check at a time, running `make test` after each. Never hardcode cells from the sample; prove each check on the generated wind workbook too.

## Gaps found when the previous phase closed

(filled by `/phase-close 0`)

<!-- The sections below are filled by /phase-close; the docs check requires them once the phase is closed. -->
