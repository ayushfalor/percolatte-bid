# Phase 3: Rivals

Status: not started

## Goal

Turn auction history and web research into frozen, explained beliefs about each rival, one snapshot per regime.

## Scope

- `app/core/rival_model.py`: `build_snapshot`, `draws`
- Behavior types from the 13 solar auctions; floors from final prices minus typical cuts
- Regime shift derived from our model (about INR 0.08/kWh per INR 1/Wp) times pass-through
- Scout agent: live web research when a key is set, dated cached dossiers otherwise
- Snapshots stored as rival runs (write-once); anonymize toggle

## Gate

`backend/evals/test_phase3_rivals.py` must pass, plus everything from earlier phases.

## Start prompt for Claude Code

Run `/phase-start 3`, then:

> Build the rival model first from history only, then add Scout dossiers. Keep every number traceable to a history row, a dossier URL or an ASSUMPTIONS entry.

## Gaps found when the previous phase closed

(filled by `/phase-close 2`)

<!-- The sections below are filled by /phase-close; the docs check requires them once the phase is closed. -->
