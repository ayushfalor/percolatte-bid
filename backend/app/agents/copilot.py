"""Agent 6, Copilot: chat about the current scenario. Tools only, no LLM arithmetic.

What-ifs become Scenario rows (visible in the UI), then the Engine reruns.
It can read the rival snapshot but never change it.
"""

from __future__ import annotations

from typing import Any

from . import AgentContext, NotBuiltYet, agent


@agent("copilot", "Copilot", "Answers what-if questions by creating scenarios and rerunning the engine", built=False)
def run(ctx: AgentContext) -> dict[str, Any]:
    raise NotBuiltYet("Copilot is not built yet")
