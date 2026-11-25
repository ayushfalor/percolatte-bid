"""Phase 1: the Auditor's deterministic core. Contract only; see evals/test_phase1_auditor.py."""

from __future__ import annotations

from typing import Any

from .contracts import Finding, Fix
from .patching import engine_for, merge
from .workbook_reader import key_cells, read_structure

SWING = 0.10  # how far each driver is moved either way, as a share of its own value
SLOPE_STEP = 0.02  # tariff step used to measure the local IRR slope
EXACT_ROWS = 3  # how many of the top drivers get a real goal seek instead of the estimate
FLAT = 1e-6  # a swing at or below this is no swing at all, in INR/kWh
BRACKET = 0.25  # INR/kWh either side of the estimate, handed to the solver so it skips its own search


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


def _drivers(path: str, variable_cell: str) -> list[dict[str, Any]]:
    """Numeric inputs something actually reads, excluding the tariff we solve for."""
    inputs = read_structure(path)["inputs"]
    return [
        cell
        for cell in inputs
        if cell["dependents"] > 0
        and not cell["axis"]
        and cell["cell"] != variable_cell
        and isinstance(cell["value"], (int, float))
        and not isinstance(cell["value"], bool)
        and cell["value"] != 0
    ]


def _breakeven_slope(engine, variable: str, target: str, base_tariff: float) -> float:
    """How much the IRR moves per INR/kWh of tariff, measured locally. Two recalculations."""
    step = max(abs(base_tariff) * SLOPE_STEP, 1e-3)
    high = engine.evaluate({variable: base_tariff + step}, [target])[target]
    low = engine.evaluate({variable: base_tariff - step}, [target])[target]
    if not isinstance(high, (int, float)) or not isinstance(low, (int, float)):
        raise AuditError(f"{target} is not numeric when the tariff moves; cannot rank drivers")
    slope = (high - low) / (2 * step)
    if abs(slope) < 1e-9:
        raise AuditError(f"Moving {variable} does not move {target}; cannot rank drivers")
    return slope


def _exact_breakeven(
    engine, variable: str, target: str, target_irr: float, cell: str, value: Any, near: float
) -> float:
    """Goal seek the real breakeven, starting from the first-order estimate.

    Handing the solver a bracket around the estimate skips its own bracket search, which is what
    makes a tornado of exact numbers affordable. If the estimate was too far off to bracket the
    answer, fall back to letting the solver find its own.
    """
    override = {cell: value}
    for bounds in ({"lower": near - BRACKET, "upper": near + BRACKET}, {}):
        result = engine.goal_seek(variable, target, target_irr, overrides=override, **bounds)
        if result.converged:
            return result.value
    raise AuditError(f"Could not solve the breakeven with {cell} at {value}")


def tornado(path: str, top_n: int = 8, target_irr: float = 0.14) -> list[dict[str, Any]]:
    """Which inputs move the breakeven most: [{"cell", "label", "low", "high", "swing"}], sorted by swing.

    Labels come from the row text or the column header, whichever names the input.

    Goal seeking every input would cost a full solve each. Instead we price each input with two
    recalculations at today's tariff and convert the IRR it moves into a tariff using the local
    slope, then goal seek the few that come out on top so the numbers we show are exact.
    """
    engine = engine_for(path)
    variable, target = _seek_cells(path, engine)
    variable_cell = engine.normalize_ref(variable)
    base_tariff = float(engine.current_value(variable))
    base_irr = engine.evaluate({}, [target])[target]
    slope = _breakeven_slope(engine, variable, target, base_tariff)
    base_breakeven = breakeven_with_fixes(path, [], target_irr=target_irr)

    rows: list[dict[str, Any]] = []
    for driver in _drivers(path, variable_cell):
        value = float(driver["value"])
        ends = []
        for moved in (value * (1 - SWING), value * (1 + SWING)):
            irr = engine.evaluate({driver["cell"]: moved}, [target])[target]
            if not isinstance(irr, (int, float)):
                break
            # The tariff that puts the IRR back where it was: a first-order estimate.
            ends.append(base_breakeven - (irr - base_irr) / slope)
        if len(ends) != 2:
            continue
        low, high = min(ends), max(ends)
        rows.append(
            {
                "cell": driver["cell"],
                "label": driver["label"] or driver["cell"],
                "value": value,
                "low": low,
                "high": high,
                "swing": high - low,
                "exact": False,
            }
        )

    # An input the live scenario never reads swings by nothing. Showing it as a driver is noise.
    rows = [row for row in rows if row["swing"] > FLAT]
    rows.sort(key=lambda r: -r["swing"])
    rows = rows[:top_n]
    for row in rows[:EXACT_ROWS]:
        ends = sorted(
            _exact_breakeven(engine, variable, target, target_irr, row["cell"], moved, estimate)
            for moved, estimate in (
                (row["value"] * (1 - SWING), row["low"]),
                (row["value"] * (1 + SWING), row["high"]),
            )
        )
        row["low"], row["high"] = ends
        row["swing"] = ends[1] - ends[0]
        row["exact"] = True
    rows.sort(key=lambda r: -r["swing"])
    return rows
