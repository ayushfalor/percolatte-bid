Start phase $ARGUMENTS of the Bid Workbench.

1. Read CLAUDE.md, docs/phases/PLAN.md, docs/phases/status.json, docs/solution/SOLUTION.md and docs/phases/phase-$ARGUMENTS.md.
2. Read the gate tests for this phase in backend/evals/ (files named test_phase$ARGUMENTS_*.py) and the contracts in backend/app/core/contracts.py.
3. Compare the gate tests with the phase scope. List, in plain English:
   - scope items with no test,
   - tests that are wrong, too weak, or depend on the sample's exact cells where they should not,
   - anything in SOLUTION.md this phase contradicts.
4. Propose the test changes. Do not write product code yet. Wait for my OK.
5. After my OK: commit the test changes on branch phase-$ARGUMENTS, then build in small steps, running `make test` after each step and committing when green.
