# Phase 5: UX and Copilot

Status: not started

## Goal

A bid manager can act without us in the room: three numbers, the bridge, the ladder, the replay, every number one click from its source; chat for what-ifs.

## Scope

- Screens: Setup timeline, Bid Brief, War Room, Rivals, Audit and X-ray, Tender, Assumptions
- Copilot with tools only; `app/core/grounding.py` blocks numbers no tool produced
- What-ifs saved as scenarios and shown as ghost curves
- Browser smoke test of the main screens

## Gate

`backend/evals/test_phase5_copilot_ui.py` must pass, plus everything from earlier phases.

## Start prompt for Claude Code

Run `/phase-start 5`, then:

> Build the Bid Brief and War Room first, then the Copilot. Keep the UI reading only from the API, never computing numbers itself.

## Gaps found when the previous phase closed

(filled by `/phase-close 4`)

<!-- The sections below are filled by /phase-close; the docs check requires them once the phase is closed. -->
