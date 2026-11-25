"""Agent 4, Rival model: per rival, how likely they bid at what price, and why.

Output is a frozen snapshot: runs are never modified after they finish, so a
rival snapshot is immutable by construction. New beliefs = a new run (v2).
"""
from __future__ import annotations

from typing import Any

from . import AgentContext, NotBuiltYet, agent


@agent("rival", "Rival model", "Per rival: chance of bidding at each price and why (frozen once computed)", built=False)
def run(ctx: AgentContext) -> dict[str, Any]:
    raise NotBuiltYet("Rival model is not built yet")
