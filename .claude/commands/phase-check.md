Check the current state against the evals.

1. Run `make test` (fast suite). If Docker is running, also run `make eval`.
2. Report in a short table: passed, failed, expected failures (xfail) and unexpected passes (xpass), grouped by phase marker.
3. For each failure in a closed phase or the current phase: the test, the likely cause, the smallest fix.
4. Do not change tests to make them pass. If a test is wrong, say why and ask me.
