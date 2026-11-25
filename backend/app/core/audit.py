"""Phase 1: the Auditor's deterministic core. Contract only; see evals/test_phase1_auditor.py."""
from __future__ import annotations

from typing import Any

from .contracts import Finding


def audit_workbook(path: str, tender_facts: list[Any] | None = None) -> list[Finding]:
    """Return every finding, each with evidence, severity, INR/kWh impact and a fix-as-scenario.

    Must work on any workbook (no hardcoded cells). Checks: hardcode inside a formula row,
    truncated ranges vs sibling aggregates, unused inputs, cosmetic inputs, stale notes,
    whole-number percents, legacy sheets, and (with tender facts) tender-vs-model mismatches.
    """
    raise NotImplementedError("Phase 1: Auditor not built yet")


def corrected_breakeven(path: str, target_irr: float = 0.14) -> float:
    """Breakeven tariff after applying every 'high' finding's fix as overrides."""
    raise NotImplementedError("Phase 1: Auditor not built yet")


def tornado(path: str, top_n: int = 8) -> list[dict[str, Any]]:
    """Which inputs move the breakeven most: [{"cell", "label", "low", "high", "swing"}], sorted by swing."""
    raise NotImplementedError("Phase 1: Auditor not built yet")
