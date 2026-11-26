"""Phase 1: the Auditor's deterministic core. Contract only; see evals/test_phase1_auditor.py."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from openpyxl import load_workbook

from . import checks
from .contracts import Finding, Fix
from .excel_engine import EngineError
from .model_map import formula_runs
from .patching import engine_for, file_hash, merge
from .workbook_reader import hurdle_for, key_cells, read_structure

SWING = 0.10  # how far each driver is moved either way, as a share of its own value
SLOPE_STEP = 0.02  # tariff step used to measure the local IRR slope
EXACT_ROWS = 3  # how many of the top drivers get a real goal seek instead of the estimate
FLAT = 1e-6  # a swing at or below this is no swing at all, in INR/kWh
BRACKET = 0.25  # INR/kWh either side of the estimate, handed to the solver so it skips its own search
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
GRAPH_BASED = {"orphan_input", "cosmetic_input", "legacy_sheet"}  # findings that rest on "nothing reads this"
CHECKS = (
    checks.typed_over_findings,
    checks.truncated_range_findings,
    checks.unused_input_findings,
    checks.stale_note_findings,
    checks.whole_number_percent_findings,
    checks.legacy_sheet_findings,
    checks.unsupported_function_findings,
    checks.circular_reference_findings,
)


class AuditError(ValueError):
    """The workbook does not give us what we need to price anything."""


def _seek_cells(path: str, engine, cells: dict[str, str] | None = None) -> tuple[str, str]:
    """The tariff input to move and the equity IRR to hit. Explicit `cells` win over labels."""
    found = {**key_cells(path, engine.defined_names), **(cells or {})}
    missing = [
        f"the {name} ({hint})"
        for key, name, hint in (
            ("tariff", "tariff input", "a label containing 'tariff', or a defined name Tariff"),
            ("equity_irr", "equity IRR output", "a label like 'Equity IRR' or 'IRR to equity'"),
        )
        if not found.get(key)
    ]
    if missing:
        raise AuditError(
            "Could not find " + " and ".join(missing) + ". Pass the cells explicitly, for example "
            "tariff_cell='Inputs!C12' and irr_cell='Returns!C8'."
        )
    return found["tariff"], found["equity_irr"]


def _hurdle(path: str, target_irr: float | None) -> float:
    return hurdle_for(path) if target_irr is None else target_irr


def _model(path: str, target_irr: float, cells: dict[str, str] | None = None) -> checks.Model:
    """Read the workbook once and hand every check the same picture of it."""
    engine = engine_for(path)
    base = breakeven_with_fixes(path, [], target_irr=target_irr, cells=cells)

    untrusted = {cell for cells in engine.unsupported.values() for cell in cells}

    def price(fix: Fix) -> float | None:
        # A fix that lands on a cell we cannot evaluate has no honest price.
        if untrusted & set(fix.touches):
            return None
        try:
            return breakeven_with_fixes(path, [fix], target_irr=target_irr, cells=cells) - base
        except (AuditError, EngineError, ValueError):
            return None

    return checks.Model(
        path=path,
        book=load_workbook(path, data_only=False),
        structure=read_structure(path),
        runs=formula_runs(path),
        value_of=engine.current_value,
        price=price,
        breakeven=base,
        tariff=engine.normalize_ref(_seek_cells(path, engine, cells)[0]),
        unsupported=engine.unsupported,
        cycle_report=engine.cycle_report,
    )


def audit_workbook(
    path: str,
    tender_facts: list[Any] | None = None,
    target_irr: float | None = None,
    cells: dict[str, str] | None = None,
) -> list[Finding]:
    """Return every finding, each with evidence, severity, INR/kWh impact and a fix-as-scenario.

    Must work on any workbook (no hardcoded cells). Checks: hardcode inside a formula row,
    truncated ranges vs sibling aggregates, unused inputs, cosmetic inputs, stale notes,
    whole-number percents, legacy sheets, and (with tender facts) tender-vs-model mismatches.
    """
    model = _model(path, _hurdle(path, target_irr), cells)
    findings = [finding for check in CHECKS for finding in check(model)]
    findings.extend(checks.tender_findings(model, tender_facts or []))
    dynamic = checks.dynamic_references(model.book)
    if dynamic:
        findings = [_hedged(f) if f.id in GRAPH_BASED else f for f in findings]
    return sorted(findings, key=_worst_first)


def _hedged(finding: Finding) -> Finding:
    """A graph-based finding on a workbook whose graph cannot be trusted is information, not a bug."""
    return replace(finding, severity="info", evidence=finding.evidence + checks.DYNAMIC_NOTE)


def _worst_first(finding: Finding) -> tuple[int, float, str]:
    """Most serious first, then the biggest number, so the UI can show the list as it comes."""
    return (SEVERITY_ORDER[finding.severity], -abs(finding.impact_inr_per_kwh or 0.0), finding.where)


_solved: dict[str, float] = {}
_SOLVED_MAX = 256


def breakeven_with_fixes(
    path: str, fixes: list[Fix], target_irr: float | None = None, cells: dict[str, str] | None = None
) -> float:
    """Breakeven tariff with these fixes applied to a temporary copy. Never writes to `path`.

    The answer is a pure function of the file, the fixes and the hurdle, so it is remembered.
    An audit prices every fix and the corrected breakeven then applies a subset of the same
    fixes, which would otherwise solve the same thing twice.
    """
    target_irr = _hurdle(path, target_irr)
    overrides, patches = merge(fixes)
    key = json.dumps([file_hash(path), patches, overrides, target_irr, cells], sort_keys=True, default=str)
    if key in _solved:
        return _solved[key]
    engine = engine_for(path, patches)
    variable, target = _seek_cells(path, engine, cells)
    result = engine.goal_seek(variable, target, target_irr, overrides=overrides)
    if not result.converged:
        raise AuditError(f"No tariff reaches {target_irr:.0%} on {target}: {result.message}")
    if len(_solved) >= _SOLVED_MAX:
        _solved.pop(next(iter(_solved)))
    _solved[key] = result.value
    return result.value


def corrected_breakeven(
    path: str,
    tender_facts: list[Any] | None = None,
    target_irr: float | None = None,
    cells: dict[str, str] | None = None,
) -> float:
    """Breakeven tariff after applying every fix that is certain from the model or the tender.

    A fix is excluded when its impact rests on an assumed number (the finding carries
    ASSUMPTIONS ids), so the ALMM module re-price stays out of this number and lives as
    a lever instead.

    Pass the tender facts to include the model-versus-tender fixes. Without them this is the
    model checked against itself, which is all we can honestly do with no tender in hand.
    """
    findings = audit_workbook(path, tender_facts=tender_facts, target_irr=target_irr, cells=cells)
    return corrected_breakeven_from(path, findings, target_irr=target_irr, cells=cells)


def corrected_breakeven_from(
    path: str, findings: list[Finding], target_irr: float | None = None, cells: dict[str, str] | None = None
) -> float:
    """The same number from findings already in hand, so a caller does not audit twice."""
    certain = [f.fix for f in findings if _is_certain(f)]
    return breakeven_with_fixes(path, certain, target_irr=target_irr, cells=cells)


def _is_certain(finding: Finding) -> bool:
    """A fix we can apply without assuming anything, and that moves the number (D-011)."""
    return bool(finding.fix) and not finding.assumptions and bool(finding.impact_inr_per_kwh)


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


def tornado(
    path: str, top_n: int = 8, target_irr: float | None = None, cells: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Which inputs move the breakeven most: [{"cell", "label", "low", "high", "swing"}], sorted by swing.

    Labels come from the row text or the column header, whichever names the input.

    Goal seeking every input would cost a full solve each. Instead we price each input with two
    recalculations at today's tariff and convert the IRR it moves into a tariff using the local
    slope, then goal seek the few that come out on top so the numbers we show are exact.
    """
    target_irr = _hurdle(path, target_irr)
    engine = engine_for(path)
    variable, target = _seek_cells(path, engine, cells)
    variable_cell = engine.normalize_ref(variable)
    base_tariff = float(engine.current_value(variable))
    base_irr = engine.evaluate({}, [target])[target]
    slope = _breakeven_slope(engine, variable, target, base_tariff)
    base_breakeven = breakeven_with_fixes(path, [], target_irr=target_irr, cells=cells)

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
