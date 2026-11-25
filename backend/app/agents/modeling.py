"""Agent 5, Engine (module: modeling): win odds and profit at every price point.

Built so far: the economics curve (equity IRR and min DSCR across tariffs),
computed from the user's own workbook. Next: Monte Carlo against the frozen
rival snapshot using core.auction_rules, then the price ladder.
"""
from __future__ import annotations

from typing import Any

from ..core.excel_engine import get_engine
from ..core.workbook_reader import find_by_label
from . import AgentContext, agent


def _defaults(path: str, eng) -> tuple[str | None, str | None, str | None]:
    variable = "Tariff" if any(n.upper() == "TARIFF" for n in eng.defined_names) else find_by_label({}, [r"^tariff"], path)
    irr = find_by_label({}, [r"equity irr"], path)
    dscr = find_by_label({}, [r"min(imum)? dscr"], path)
    return variable, irr, dscr


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

    points, n = [], int(round((stop - start) / step)) + 1
    for i in range(n):
        tariff = round(start + i * step, 4)
        values = eng.evaluate({**overrides, variable: tariff}, outputs)
        points.append({"tariff": tariff, "equity_irr": values.get(eng.normalize_ref(irr_cell)),
                       "min_dscr": values.get(eng.normalize_ref(dscr_cell)) if dscr_cell else None})
        ctx.progress((i + 1) / (n + 2), f"Priced {i + 1} of {n} tariffs")

    hurdle = float(ctx.params.get("hurdle", 0.14))
    seek = eng.goal_seek(variable, irr_cell, hurdle, overrides=overrides)
    return {
        "variable": eng.normalize_ref(variable),
        "irr_cell": eng.normalize_ref(irr_cell),
        "dscr_cell": eng.normalize_ref(dscr_cell) if dscr_cell else None,
        "hurdle": hurdle,
        "breakeven_tariff": seek.value,
        "curve": points,
        "next": "Monte Carlo win odds against the frozen rival snapshot (not built yet)",
    }
