"""Agent 5, Engine (module: modeling): win odds and profit at every price point.

Built so far: the economics curve (equity IRR and min DSCR across tariffs),
computed from the user's own workbook. Next: Monte Carlo against the frozen
rival snapshot using core.auction_rules, then the price ladder.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..core.contracts import RivalProfile, RivalSnapshot
from ..core.excel_engine import get_engine
from ..core.simulate import price_ladder, recommend
from ..core.workbook_reader import key_cells
from . import AgentContext, agent


def _defaults(path: str, eng) -> tuple[str | None, str | None, str | None]:
    cells = key_cells(path, eng.defined_names)
    return cells["tariff"], cells["equity_irr"], cells["min_dscr"]


@agent("engine", "Engine", "Win odds and profit at every price point; how they move with inputs")
def run(ctx: AgentContext) -> dict[str, Any]:
    _, path = ctx.document()
    eng = get_engine(path)
    variable, irr_cell, dscr_cell = _defaults(path, eng)
    variable = ctx.params.get("variable", variable)
    irr_cell = ctx.params.get("irr_cell", irr_cell)
    dscr_cell = ctx.params.get("dscr_cell", dscr_cell)
    if not variable or not irr_cell:
        raise ValueError("Could not find the tariff input or equity IRR output; pass variable and irr_cell")

    start = float(ctx.params.get("start", 2.0))
    stop = float(ctx.params.get("stop", 2.8))
    step = float(ctx.params.get("step", 0.05))
    overrides = ctx.params.get("overrides", {})
    outputs = [c for c in (irr_cell, dscr_cell) if c]

    points, n = [], round((stop - start) / step) + 1
    for i in range(n):
        tariff = round(start + i * step, 4)
        values = eng.evaluate({**overrides, variable: tariff}, outputs)
        points.append(
            {
                "tariff": tariff,
                "equity_irr": values.get(eng.normalize_ref(irr_cell)),
                "min_dscr": values.get(eng.normalize_ref(dscr_cell)) if dscr_cell else None,
            }
        )
        ctx.progress((i + 1) / (n + 2), f"Priced {i + 1} of {n} tariffs")

    hurdle = float(ctx.params.get("hurdle", 0.14))
    seek = eng.goal_seek(variable, irr_cell, hurdle, overrides=overrides)
    dscr_floor = float(ctx.params.get("dscr_floor", 1.20))  # A-02
    dscr_seek = eng.goal_seek(variable, dscr_cell, dscr_floor, overrides=overrides) if dscr_cell else None
    result: dict[str, Any] = {
        "variable": eng.normalize_ref(variable),
        "irr_cell": eng.normalize_ref(irr_cell),
        "dscr_cell": eng.normalize_ref(dscr_cell) if dscr_cell else None,
        "hurdle": hurdle,
        "breakeven_tariff": seek.value,
        "dscr_tariff": dscr_seek.value if dscr_seek and dscr_seek.converged else None,
        "curve": points,
    }
    result.update(_ladder(ctx, points, seek.value, result["dscr_tariff"]))
    return result


def _ladder(
    ctx: AgentContext, curve: list[dict[str, Any]], hurdle_tariff: float | None, dscr_tariff: float | None
) -> dict[str, Any]:
    """Win odds and the three numbers, if a rival snapshot exists. Rivals do not see our costs."""
    rival = ctx.latest_result("rival") or {}
    regime = str(ctx.params.get("regime", "almm_40"))
    stored = rival.get("snapshots", {}).get(regime)
    if not stored or hurdle_tariff is None:
        return {"ladder": [], "recommendation": None, "snapshot_id": None, "why_no_ladder": "no rival run yet"}
    snapshot = RivalSnapshot(**{**stored, "profiles": [RivalProfile(**p) for p in stored["profiles"]]})
    ctx.progress(0.9, f"Playing the auction 5,000 times at every price ({regime})")
    ladder = price_ladder(snapshot, curve, our_mw=float(ctx.params.get("our_mw", 200)))
    rec = recommend(ladder, hurdle_tariff=hurdle_tariff, dscr_tariff=dscr_tariff)
    return {
        "ladder": [asdict(p) for p in ladder],
        "recommendation": asdict(rec),
        "snapshot_id": snapshot.id,
        "regime": regime,
    }
