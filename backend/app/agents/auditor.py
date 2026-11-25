"""Agent 2, Auditor: model bugs, tender-vs-model mismatches, data-quality log.

Not built yet. What it must find is already written down as tests in
evals/test_targets.py (marked xfail until this agent exists).
"""

from __future__ import annotations

from typing import Any

from . import AgentContext, NotBuiltYet, agent


@agent("auditor", "Auditor", "Finds model bugs and tender mismatches, prices each fix in INR/kWh", built=False)
def run(ctx: AgentContext) -> dict[str, Any]:
    raise NotBuiltYet("Auditor is not built yet (see evals/test_targets.py)")
