"""Phase 4: Monte Carlo price ladder, recommendation and replay. Contract only.

See evals/test_phase4_engine.py. Uses core.auction_rules for every rule; never re-implements them.
"""

from __future__ import annotations

from typing import Any

from .contracts import LadderPoint, Recommendation, RivalSnapshot


def price_ladder(
    snapshot: RivalSnapshot,
    economics: list[dict[str, Any]],
    our_mw: float = 200,
    tendered_mw: float = 700,
    start: float = 2.00,
    stop: float = 2.80,
    step: float = 0.01,
    seed: int = 42,
) -> list[LadderPoint]:
    """Win odds (from the rival draws) joined with profit (from the workbook) at every price.

    economics rows: {"tariff", "equity_irr", "min_dscr", optional "npv_cr"}, as produced by the
    Engine agent's economics curve. Interpolate between rows; never call the workbook here.
    """
    raise NotImplementedError("Phase 4: Monte Carlo not built yet")


def recommend(
    ladder: list[LadderPoint], hurdle_tariff: float, dscr_tariff: float | None = None, max_h1_risk: float = 0.05
) -> Recommendation:
    """walk_away = max(hurdle_tariff, dscr_tariff); target band = best expected value above it."""
    raise NotImplementedError("Phase 4: Monte Carlo not built yet")


def replay(
    snapshot: RivalSnapshot, draw_index: int, our_open: float, our_floor: float, our_mw: float = 200
) -> list[dict[str, Any]]:
    """Tick-by-tick e-RA for the war room: 1 paisa cuts, 30 min + 8 min extensions on zone change."""
    raise NotImplementedError("Phase 4: Monte Carlo not built yet")
