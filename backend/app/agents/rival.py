"""Agent 4, Rival model: per rival, how likely they bid at what price, and why.

Output is a frozen snapshot per regime: runs are never modified after they finish, so a rival
snapshot is immutable by construction. New beliefs = a new run.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..core.history_reader import read_history
from ..core.rival_model import REGIMES, SHIFT_INR_PER_KWH, build_snapshot
from . import AgentContext, agent


@agent("rival", "Rival model", "Per rival: chance of bidding at each price and why (frozen once computed)")
def run(ctx: AgentContext) -> dict[str, Any]:
    doc, path = ctx.document()
    if doc.kind != "history":
        raise ValueError("The rival model runs on the auction history workbook")
    ctx.progress(0.1, "Cleaning the auction history")
    history = read_history(path)
    seed = int(ctx.params.get("seed", ctx.settings.sim_seed))
    snapshots = {}
    for i, regime in enumerate(REGIMES):
        ctx.progress(0.3 + 0.2 * i, f"Drawing the field for the {regime} regime")
        snapshots[regime] = asdict(build_snapshot(history, regime, seed=seed))
    return {
        "seed": seed,
        "shift_inr_per_kwh": SHIFT_INR_PER_KWH,
        "rivals": len(history["solar_ists"]["groups"]),
        "snapshots": snapshots,
    }
