"""Agent 3, Scout: web research on rivals. Facts with URL and date, no probabilities.

Live mode: Claude with the server-side web search tool. Offline mode: load the
dated snapshot committed in data/snapshots/ so the demo runs without keys.
"""

from __future__ import annotations

from typing import Any

from . import AgentContext, NotBuiltYet, agent


@agent("scout", "Scout", "Researches rivals on the web: wins, tariffs, module sourcing, balance sheet", built=False)
def run(ctx: AgentContext) -> dict[str, Any]:
    raise NotBuiltYet("Scout is not built yet")
