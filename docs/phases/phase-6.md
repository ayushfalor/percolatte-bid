# Phase 6: Deploy and DB

Status: not started

## Goal

Running on the internet with a real database, backed up, deployed by CI, and a finished README.

## Scope

- Production compose override or platform config; secrets in the host, not the repo
- Postgres: managed, or the VM container with nightly `scripts/backup-db.sh`
- CD: deploy on a `v*` tag, then smoke test against `DEPLOY_URL`
- README: what we built and why, what we left out, where it breaks, LLM cost, the product page

## Gate

`backend/evals/test_phase6_deploy.py` must pass, plus everything from earlier phases.

## Start prompt for Claude Code

Run `/phase-start 6`, then:

> Pick the hosting option in PLAN.md, write the deploy workflow, add the backup script, run the live smoke test, finish the README.

## Gaps found when the previous phase closed

(filled by `/phase-close 5`)

<!-- The sections below are filled by /phase-close; the docs check requires them once the phase is closed. -->
