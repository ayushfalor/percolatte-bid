# Phase plan

We build in phases. Each phase has a goal, a set of evals that must pass (its gate), and a doc that
explains it and answers the questions a reviewer will ask. CI runs on every push and never turns off.

## The loop (every phase, same steps)

1. **Check the gate before building.** Open Claude Code and run `/phase-start N`. It re-reads this
   plan, `docs/solution/SOLUTION.md` and `docs/phases/phase-N.md`, compares the phase's evals with its
   scope, and lists missing or wrong evals. Fix the evals first and commit them.
2. **Build in small steps** on a branch `phase-N`. After each step Claude Code runs the fast evals
   (`make test`). Commit when green.
3. **Check against the evals**: `/phase-check`. It runs the fast suite and the Docker suite and
   reports pass/fail per phase.
4. **Close the phase**: `/phase-close N`. It bumps `status.json` (the phase's tests become mandatory),
   fills the phase doc (what we built, how to check it, eval results, decisions, questions they may
   ask), updates README status, ASSUMPTIONS and the decision log.
5. **Look ahead**: as part of closing, it reviews phase N+1's evals against its scope and writes the
   gaps into `phase-(N+1).md`.
6. **Pull request**. CI must be green. Merge to `main`, tag `phase-N`.

## The gate, mechanically

- Tests carry `@pytest.mark.phase(N)`. While `status.json` says `completed < N`, they are expected
  failures and do not break CI. Once the phase is closed, they must pass, forever.
- `evals/test_docs.py` fails CI if a closed phase's doc is missing a required section or has fewer
  than 6 reviewer questions with answers.

## Phases

| Phase | Goal | Gate (evals) | Est. hours |
|---|---|---|---|
| 0 Foundation | Repo, Docker, 3 tables, async worker, Reader, formula engine, auction rules, CI, docs | Everything not marked with a later phase | done |
| 1 Model understanding | Auditor: findings priced in paise with fixes; corrected breakeven; tornado; better labels | `test_phase1_auditor.py` | 3 to 4 |
| 2 Tender intelligence | LLM facts with verified quotes, unusual clauses, offline cache, cost logging, model-vs-tender checks | `test_phase2_tender.py` | 3 |
| 3 Rivals | History calibration, Scout dossiers (live or cached), frozen snapshots per regime | `test_phase3_rivals.py` | 3 |
| 4 Engine | Monte Carlo ladder, recommendation, replay | `test_phase4_engine.py` | 3 to 4 |
| 5 UX and Copilot | Bid Brief, War Room, Rivals, Audit, Tender, Assumptions; chat with grounded numbers | `test_phase5_copilot_ui.py` | 4 to 5 |
| 6 Deploy and DB | Production config, managed or backed-up Postgres, CD on tag, live smoke test, final README | `test_phase6_deploy.py` | 2 to 3 |

Total about 19 to 22 hours. If the 24-hour clock is running, cut in this order: live Scout (use the
cached dossiers), replay polish, live war-room assist, extra UI screens beyond Bid Brief and War Room.

## CI/CD (always on)

- **Every push and pull request**: fast evals (no Docker, about 2 minutes), then the full stack in
  Docker exactly as a reviewer runs it, then the smoke test.
- **Protect `main`**: in GitHub settings, require both CI jobs to pass before merging.
- **CD** is added in Phase 6: deploy on a `v*` tag, then run the live smoke test against the URL.

## Phase 6 options (decide at its start)

- **One small VM** with the same `docker compose` plus Caddy for HTTPS and a nightly `pg_dump`.
  Same as local, cheapest, needs a server.
- **A managed platform** (for example Render or Railway) with managed Postgres. No server to look
  after, a little more setup per service.

## Working with Claude Code

- `CLAUDE.md` at the repo root is read automatically: project rules, commands, where docs live.
- Custom commands in `.claude/commands/`: `/phase-start N`, `/phase-check`, `/phase-close N`,
  `/explain <topic>`.
- After each phase you can paste the phase doc and the CI result back into Claude.ai for a review.
