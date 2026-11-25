"""Shared data shapes for every agent. Phases fill in the functions; these shapes stay stable.

If you change a field here, update the evals and docs/solution/SOLUTION.md in the same commit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["high", "medium", "low", "info"]


@dataclass(frozen=True)
class Finding:
    """One thing the Auditor found (Phase 1)."""
    id: str  # e.g. "orphan_input", "truncated_range", "tender_mismatch"
    where: str  # a cell ("Inputs!C28") or a sheet name ("Inputs_old_v2")
    severity: Severity
    title: str  # plain English, one line
    evidence: str  # the formula, comment or value that proves it
    impact_inr_per_kwh: float | None = None  # change in 14% breakeven tariff if fixed
    fix: dict[str, Any] | None = None  # overrides that apply the fix as a scenario (never edits the file)


@dataclass(frozen=True)
class TenderFact:
    """One fact pulled from the RfS (Phase 2). Every fact carries its proof."""
    field: str
    value: Any
    unit: str
    clause: str
    pdf_page: int
    printed_page: int | None
    quote: str
    verified: bool  # the quote was found on the cited page by code, not by the LLM
    source: Literal["llm", "rule", "cache"] = "llm"


@dataclass(frozen=True)
class RivalProfile:
    """What we believe about one rival (Phase 3). The 'why' is part of the output."""
    name: str  # display label; real names are illustrative, see ASSUMPTIONS.md
    archetype: Literal["leader", "mid_pack", "laggard", "wildcard"]
    p_participate: float
    capacity_mw: list[tuple[float, float]]  # [(MW, probability), ...]
    floor_p10: float
    floor_p50: float
    floor_p90: float
    why: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RivalSnapshot:
    """Frozen once computed (Phase 3). New beliefs mean a new snapshot, never an edit."""
    id: str
    regime: Literal["history", "almm_40", "almm_100"]
    seed: int
    n_draws: int
    profiles: list[RivalProfile]
    sha256: str  # hash of the draws; must never change for a given id


@dataclass(frozen=True)
class LadderPoint:
    """One row of the price ladder (Phase 4)."""
    tariff: float
    p_win_any: float
    p_win_full: float
    expected_mw: float
    p_h1_eliminated: float
    equity_irr: float | None
    min_dscr: float | None
    npv_cr: float | None  # equity value above the hurdle, INR crore, if we win the full capacity
    expected_value_cr: float | None


@dataclass(frozen=True)
class Recommendation:
    """The three numbers the bid manager acts on (Phase 4)."""
    entry_bid: float  # envelope-2 tariff
    target_low: float
    target_high: float
    walk_away: float  # never bid below this in the e-RA
    reasons: list[str] = field(default_factory=list)
