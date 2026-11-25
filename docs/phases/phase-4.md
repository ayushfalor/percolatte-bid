# Phase 4: Engine

Status: not started

## Goal

Play the auction thousands of times under the RfS rules and turn it into a price ladder and three numbers.

## Scope

- `app/core/simulate.py`: `price_ladder`, `recommend`, `replay`
- Ladder mode first (fast), replay mode second (tick by tick)
- Always call `core/auction_rules.py`; never re-implement a rule
- Common random numbers and a fixed seed
- Engine agent stores the ladder and recommendation as a run

## Gate

`backend/evals/test_phase4_engine.py` must pass, plus everything from earlier phases.

## Start prompt for Claude Code

Run `/phase-start 4`, then:

> Build the Monte Carlo ladder against the Phase 3 snapshot, then the recommendation, then the replay. Watch the runtime budget.

## Gaps found when the previous phase closed

(filled by `/phase-close 3`)

<!-- The sections below are filled by /phase-close; the docs check requires them once the phase is closed. -->
