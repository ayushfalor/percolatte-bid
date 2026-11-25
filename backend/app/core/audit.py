"""Phase 1: the Auditor's deterministic core. Contract only; see evals/test_phase1_auditor.py."""

from __future__ import annotations

from typing import Any

from .contracts import Finding, Fix
from .patching import engine_for, merge
from .workbook_reader import key_cells


class AuditError(ValueError):
    """The workbook does not give us what we need to price anything."""


def _seek_cells(path: str, engine) -> tuple[str, str]:
    """The tariff input to move and the equity IRR to hit."""
    cells = key_cells(path, engine.defined_names)
    variable, target = cells["tariff"], cells["equity_irr"]
    if not variable or not target:
        raise AuditError("Could not find a tariff input and an equity IRR output in this workbook")
    return variable, target


def audit_workbook(path: str, tender_facts: list[Any] | None = None) -> list[Finding]:
    """Return every finding, each with evidence, severity, INR/kWh impact and a fix-as-scenario.

    Must work on any workbook (no hardcoded cells). Checks: hardcode inside a formula row,
    truncated ranges vs sibling aggregates, unused inputs, cosmetic inputs, stale notes,
    whole-number percents, legacy sheets, and (with tender facts) tender-vs-model mismatches.
    """
    raise NotImplementedError("Phase 1: Auditor not built yet")


def breakeven_with_fixes(path: str, fixes: list[Fix], target_irr: float = 0.14) -> float:
    """Breakeven tariff with these fixes applied to a temporary copy. Never writes to `path`."""
    overrides, patches = merge(fixes)
    engine = engine_for(path, patches)
    variable, target = _seek_cells(path, engine)
    result = engine.goal_seek(variable, target, target_irr, overrides=overrides)
    if not result.converged:
        raise AuditError(f"No tariff reaches {target_irr:.0%} on {target}: {result.message}")
    return result.value


def corrected_breakeven(path: str, target_irr: float = 0.14) -> float:
    """Breakeven tariff after applying every fix that is certain from the model or the tender.

    A fix is excluded when its impact rests on an assumed number (the finding carries
    ASSUMPTIONS ids), so the ALMM module re-price stays out of this number and lives as
    a lever instead.
    """
    raise NotImplementedError("Phase 1: Auditor not built yet")


def tornado(path: str, top_n: int = 8) -> list[dict[str, Any]]:
    """Which inputs move the breakeven most: [{"cell", "label", "low", "high", "swing"}], sorted by swing.

    Labels come from the row text or the column header, whichever names the input (Phase 1).
    """
    raise NotImplementedError("Phase 1: Auditor not built yet")
