Close phase $ARGUMENTS.

1. Run `make test` and `make eval`. Every test for phase $ARGUMENTS must pass. If not, stop and report.
2. Set "completed" to $ARGUMENTS and "current" to the next phase in docs/phases/status.json. Run `make test` again: the phase's tests are now mandatory.
3. Update docs/phases/phase-$ARGUMENTS.md: set Status to done and fill these sections:
   - ## What we built (plain English, then the files)
   - ## How to check it (commands and URLs a reviewer can run)
   - ## Eval results (counts from the runs above, and what each group proves)
   - ## Decisions (link to entries you added in docs/solution/decisions.md)
   - ## Questions they may ask: 8 to 12 likely reviewer questions as **Q:** / **A:**, answers in plain semi-technical English, each answer pointing to a file, test or number
4. Update README (agent status table, any new commands), ASSUMPTIONS.md (new assumptions), docs/problem/02-requirements.md (status column).
5. Look ahead: compare the next phase's gate tests with its scope and write the gaps under "Gaps found when the previous phase closed" in its doc.
6. Run `make test` once more (the docs check must pass), then propose a commit message and PR description.
