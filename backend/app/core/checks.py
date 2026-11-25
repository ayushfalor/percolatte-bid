"""The Auditor's individual checks. Each one takes the model and returns findings.

Nothing here names a sheet or a cell. Every check works from the shape of the workbook
(see model_map) and from the labels the model gives its own cells, so the same code finds
the same problems in a workbook it has never seen.

Pricing is injected, not imported, so these stay free of the goal-seek machinery.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter, range_boundaries

from .contracts import Finding, Fix
from .model_map import Run, operating_cost, typed_over

AGGREGATES = ("IRR", "XIRR", "NPV", "SUM", "MIN", "MAX", "AVERAGE", "MEDIAN", "COUNT")
REFERENCE_WORDS = re.compile(r"\b(target|hurdle|goal|benchmark|threshold|covenant)\b", re.I)
TOTAL_WORDS = re.compile(r"\b(total|cost|capex|capital|investment|project cost)\b", re.I)
PERCENT_OF = re.compile(r"%\s*of\s+([a-z ]+?)(?:\s+p\.?a\.?)?$", re.I)
STALE_CUE = re.compile(r"last run|previously|earlier|stale|as of|\bwas\b|\bgave\b", re.I)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
PER_UNIT = re.compile(r"/\s*(mw|mwp|kw|wp|unit|kwh)\b", re.I)
WHOLE_DECLARED = re.compile(r"whole|integer|\bno\.?\b", re.I)
MODULE_PRICE = re.compile(r"(?:INR|Rs\.?)\s*([\d.]+)\s*/\s*Wp", re.I)

CURRENT_TOKEN = "{current}"  # what an append patch expands to; see contracts.Fix

STALE_BAND = 0.20  # a noted number this close to the live answer is talking about the same thing
STALE_TOLERANCE = 0.005  # and this far from it is out of date
BIG_IMPACT = 0.01  # INR/kWh; a mismatch worth at least a paisa is a high finding


@dataclass
class Model:
    """Everything the checks read, gathered once."""

    path: str
    book: Any
    structure: dict[str, Any]
    runs: list[Run]
    value_of: Callable[[str], Any]
    price: Callable[[Fix], float | None]
    breakeven: float
    tariff: str = ""
    unsupported: dict[str, list[str]] = field(default_factory=dict)
    cycle_report: list[dict[str, Any]] = field(default_factory=list)

    @property
    def untrusted_cells(self) -> set[str]:
        """Cells our formula library cannot evaluate, so nothing downstream of them is a number."""
        return {cell for cells in self.unsupported.values() for cell in cells}


def _ref(sheet: str, coord: str) -> str:
    return f"{sheet}!{coord}"


def _absolute(ref: str) -> str:
    sheet, coord = ref.rsplit("!", 1)
    row, col = coordinate_to_tuple(coord)
    return f"{sheet}!${get_column_letter(col)}${row}"


def _line_name(run: Run) -> str:
    return f"row {run.line}" if run.across else f"column {get_column_letter(run.line)}"


def _fmt(value: Any) -> str:
    if isinstance(value, float) and abs(value) < 1:
        return f"{value:.2%}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value}"


def _severity_for(impact: float | None, when_priced: str, when_not: str) -> str:
    return when_priced if impact is not None else when_not


# ---------- a number typed over a formula ----------


def typed_over_findings(model: Model) -> list[Finding]:
    findings = []
    for run, coord in typed_over(model.path, model.runs):
        ref = _ref(run.sheet, coord)
        restored = run.formula_at(coord).lstrip("=")
        fix = Fix(
            formula_patches={ref: restored},
            note="Put the row's own formula back. Typing today's answer in would go stale.",
        )
        impact = model.price(fix)
        findings.append(
            Finding(
                id="hardcode_in_formula_row",
                where=ref,
                severity="high",
                title=f"A number is typed over the formula in {run.sheet} {_line_name(run)}",
                evidence=(
                    f"{ref} holds {_fmt(model.value_of(ref))}. Every other cell from {run.cells[0]} to "
                    f"{run.cells[-1]} holds ={restored}, which here gives {_fmt(_with(model, fix, ref))}."
                ),
                impact_inr_per_kwh=impact,
                fix=fix,
            )
        )
    return findings


def _with(model: Model, fix: Fix, ref: str) -> Any:
    """What a cell reads once a fix is applied. Free when the fix was already priced."""
    from .patching import engine_for, merge

    _, patches = merge([fix])
    return engine_for(model.path, patches).current_value(ref)


# ---------- an aggregate that stops short of its own data ----------


def _ranges_in(formula: str) -> list[str]:
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return []
    return [t.value for t in tokens if t.type == Token.OPERAND and t.subtype == Token.RANGE and ":" in t.value]


def _extend(model: Model, sheet: str, text: str, origin: tuple[str, int, int]) -> tuple[str, str] | None:
    """If this range stops before its data does, the range that covers all of it.

    The aggregate's own cell usually sits right under the column it totals, so it has to be
    treated as the end of the data, not as more of it.
    """
    target, _, addr = text.rpartition("!")
    target = target.strip("'") or sheet
    if target not in model.book.sheetnames:
        return None
    try:
        min_col, min_row, max_col, max_row = range_boundaries(addr.replace("$", ""))
    except ValueError:
        return None
    if None in (min_col, min_row, max_col, max_row):
        return None
    across = min_row == max_row
    if not across and min_col != max_col:
        return None  # a block, not a series
    if max(max_col - min_col, max_row - min_row) + 1 < 3:
        return None
    ws = model.book[target]
    col, row = max_col, max_row
    while True:
        step = (col + 1, row) if across else (col, row + 1)
        if (target, step[1], step[0]) == origin:
            break
        nxt = ws.cell(row=step[1], column=step[0])
        if nxt.value is None:
            break
        col, row = step
    if (col, row) == (max_col, max_row):
        return None
    ends = f"{get_column_letter(max_col)}{max_row}", f"{get_column_letter(col)}{row}"
    return text, text.replace(ends[0], ends[1])


def truncated_range_findings(model: Model) -> list[Finding]:
    findings = []
    for ws in model.book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                    continue
                if not any(f"{name}(" in cell.value.upper() for name in AGGREGATES):
                    continue
                ref = _ref(ws.title, cell.coordinate)
                origin = (ws.title, cell.row, cell.column)
                for text in _ranges_in(cell.value):
                    found = _extend(model, ws.title, text, origin)
                    if found is None:
                        continue
                    short, full = found
                    fixed = cell.value[1:].replace(short, full)
                    fix = Fix(formula_patches={ref: fixed}, note="Cover the whole series the model already holds.")
                    findings.append(
                        Finding(
                            id="truncated_range",
                            where=ref,
                            severity="medium",
                            title=f"{ref} aggregates a range that stops before the data does",
                            evidence=(
                                f"{cell.value} covers {short} but the series runs to {full.rsplit(':', 1)[1]}. "
                                f"It reads {_fmt(model.value_of(ref))} now and "
                                f"{_fmt(_with(model, fix, ref))} over the full range."
                            ),
                            impact_inr_per_kwh=model.price(fix),
                            fix=fix,
                        )
                    )
    return findings


# ---------- inputs nothing reads ----------


def _horizon(model: Model) -> int | None:
    """How many periods the model runs for, taken from the length of its filled-across rows."""
    lengths = Counter(len(run.cells) for run in model.runs)
    return lengths.most_common(1)[0][0] if lengths else None


def _wiring_base(model: Model, noun: str) -> dict[str, Any] | None:
    """The total a "% of <noun>" input should be charged against.

    The cells named after the noun are usually rates per MW. What we want is the total they feed:
    a scalar, not one period of a series, whose own caption says it is a total.
    """
    seeds = _named_after(model, noun)
    in_a_run = {ref for run in model.runs for ref in run.refs}
    units = {e["cell"]: e.get("unit") or "" for e in model.structure["inputs"]}
    candidates = []
    for ws in model.book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                ref = _ref(ws.title, cell.coordinate)
                if ref in in_a_run or not isinstance(cell.value, str) or not cell.value.startswith("="):
                    continue
                reads = {f"{s}!{c}" for s, c in _refs_of(model, cell.value, ws.title)}
                if not reads & seeds:
                    continue
                label = _label_of(model, ref)
                if not label or not TOTAL_WORDS.search(label) or PER_UNIT.search(units.get(ref, "")):
                    continue
                value = model.value_of(ref)
                if isinstance(value, (int, float)) and value:
                    candidates.append({"cell": ref, "label": label, "value": float(value)})
    if not candidates:
        return None
    # The total is the biggest thing the rate feeds. A multiplier sitting at 1.0 is not it.
    return max(candidates, key=lambda c: abs(c["value"]))


def _named_after(model: Model, noun: str) -> set[str]:
    """Every cell the model itself calls by this name, formulas included.

    Reading only the numeric inputs would miss Inputs!C16 "Capex", which is a link to the capex
    sheet rather than a typed number, and that is the cell the project total is built from.
    """
    wanted = noun.lower()
    found = set()
    for ws in model.book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None or (isinstance(cell.value, str) and not cell.value.startswith("=")):
                    continue
                label = _label_of(model, _ref(ws.title, cell.coordinate))
                if label and wanted in label.lower():
                    found.add(_ref(ws.title, cell.coordinate))
    return found


def _refs_of(model: Model, formula: str, sheet: str):
    from .workbook_reader import formula_refs, sheet_extents

    names = {name.upper(): dn.attr_text for name, dn in model.book.defined_names.items()}
    return formula_refs(formula, sheet, names, sheet_extents(model.book))


def _label_of(model: Model, ref: str) -> str | None:
    from .workbook_reader import label_for

    return label_for(model.book, ref)


def _wire_percent_of(model: Model, entry: dict[str, Any]) -> tuple[Fix, str] | None:
    """Charge an unwired "% of something" input in the cost row it belongs in."""
    text = f"{entry.get('unit') or ''} {entry.get('label') or ''}"
    match = PERCENT_OF.search((entry.get("unit") or "").strip()) or PERCENT_OF.search(text.strip())
    if not match:
        return None
    base = _wiring_base(model, match.group(1).strip())
    if base is None:
        return None
    found = operating_cost(model.path, model.runs, model.tariff) if model.tariff else None
    if found is None:
        return None
    run, operator = found
    # The margin's operator says how this model stores costs. "revenue + cost" means costs are
    # negative, so charging more makes the row more negative. "revenue - cost" means the opposite.
    sign = "-" if operator == "+" else "+"
    term = f"{sign}{_absolute(base['cell'])}*{_absolute(entry['cell'])}"
    fix = Fix(
        formula_patches=dict.fromkeys(run.refs, f"({CURRENT_TOKEN})" + term),
        note=f"Charge it in {run.sheet} {_line_name(run)} against {base['label']}, every period.",
    )
    return fix, base["label"]


def unused_input_findings(model: Model) -> list[Finding]:
    horizon = _horizon(model)
    findings = []
    for entry in model.structure["unreferenced_numbers"]:
        value, ref, label = entry["value"], entry["cell"], entry["label"] or entry["cell"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value == 0:
            continue
        if REFERENCE_WORDS.search(label):
            findings.append(
                Finding(
                    id="reference_value",
                    where=ref,
                    severity="info",
                    title=f"{label} is a number to aim at, not an input",
                    evidence=f"{ref} holds {_fmt(value)} and no formula reads it. That is what a target is for.",
                )
            )
            continue
        if horizon and float(value) == float(horizon):
            findings.append(
                Finding(
                    id="cosmetic_input",
                    where=ref,
                    severity="low",
                    title=f"Changing {label} does nothing",
                    evidence=(
                        f"{ref} holds {_fmt(value)} and no formula reads it. The model already runs for "
                        f"{horizon} periods because that is how many columns it has, so editing this "
                        f"cell cannot change any number."
                    ),
                    impact_inr_per_kwh=0.0,
                )
            )
            continue
        wired = _wire_percent_of(model, entry)
        comment = entry.get("comment")
        evidence = f"{ref} holds {_fmt(value)} {entry.get('unit') or ''}".strip() + " and no formula reads it."
        if comment:
            evidence += f' The note on the cell says: "{comment}".'
        if wired is None:
            findings.append(
                Finding(
                    id="orphan_input",
                    where=ref,
                    severity="medium",
                    title=f"{label} is entered but never charged",
                    evidence=evidence + " We could not work out which row it belongs in, so it is not priced.",
                )
            )
            continue
        fix, base_label = wired
        findings.append(
            Finding(
                id="orphan_input",
                where=ref,
                severity="high",
                title=f"{label} is entered but never charged",
                evidence=evidence + f" Charging it against {base_label} is what the fix does.",
                impact_inr_per_kwh=model.price(fix),
                fix=fix,
            )
        )
    return findings


# ---------- a note that no longer matches the model ----------


def stale_note_findings(model: Model) -> list[Finding]:
    live = model.breakeven
    findings = []
    for ws in model.book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                text = cell.value
                if not isinstance(text, str) or text.startswith("=") or not STALE_CUE.search(text):
                    continue
                for raw in NUMBER.findall(text):
                    noted = float(raw)
                    if not live * (1 - STALE_BAND) <= noted <= live * (1 + STALE_BAND):
                        continue
                    if abs(noted - live) <= STALE_TOLERANCE:
                        continue
                    findings.append(
                        Finding(
                            id="stale_note",
                            where=_ref(ws.title, cell.coordinate),
                            severity="medium",
                            title="A note records a number the model no longer gives",
                            evidence=f'"{text.strip()}" says {raw}, but the model breaks even at {live:.4f} today.',
                            impact_inr_per_kwh=0.0,
                        )
                    )
                    break
    return findings


# ---------- a percent that is stored unlike its neighbours ----------


def whole_number_percent_findings(model: Model) -> list[Finding]:
    by_sheet: dict[str, list[dict[str, Any]]] = {}
    for entry in model.structure["inputs"]:
        unit = entry.get("unit") or ""
        if "%" not in unit and "percent" not in (entry.get("label") or "").lower():
            continue
        by_sheet.setdefault(entry["cell"].split("!")[0], []).append(entry)

    findings = []
    for sheet, entries in by_sheet.items():
        fractions = [e for e in entries if isinstance(e["value"], (int, float)) and abs(e["value"]) < 1]
        for entry in entries:
            value, unit = entry["value"], entry.get("unit") or ""
            if not isinstance(value, (int, float)) or abs(value) <= 1 or WHOLE_DECLARED.search(unit):
                continue
            if not fractions:
                continue
            label = entry["label"] or entry["cell"]
            others = ", ".join(e["cell"].split("!")[1] for e in fractions[:4])
            findings.append(
                Finding(
                    id="whole_number_percent",
                    where=entry["cell"],
                    severity="low",
                    title=f"{label} is stored as a whole number, so it is easy to break when someone edits it",
                    evidence=(
                        f'{entry["cell"]} holds {_fmt(value)} with the unit "{unit}" and is divided by 100 '
                        f"downstream, while the other percent inputs on {sheet} ({others}) are fractions. "
                        f"Typing {value / 100:g} here would quietly change the answer."
                    ),
                    impact_inr_per_kwh=0.0,
                )
            )
    return findings


# ---------- a sheet nothing reads ----------


def legacy_sheet_findings(model: Model) -> list[Finding]:
    return [
        Finding(
            id="legacy_sheet",
            where=sheet["name"],
            severity="low",
            title=f"{sheet['name']} looks like an old copy that was left behind",
            evidence=(
                f"{sheet['name']} is {sheet['state']}, holds {sheet['numbers']} numbers and no formulas, "
                f"and nothing in the model reads it. {sheet.get('why', '')}".strip()
            ),
            impact_inr_per_kwh=0.0,
        )
        for sheet in model.structure["sheets"]
        if sheet.get("role") == "legacy_candidate"
    ]


# ---------- where the model disagrees with the tender ----------

ASSUMED_MODULE_PRICE_INR_PER_WP = 10.0  # A-03: mock import quote once ALMM does not apply


def _field(fact: Any, name: str, default: Any = None) -> Any:
    """Facts arrive as the golden dicts now and as TenderFact objects once Phase 2 lands."""
    return fact.get(name, default) if isinstance(fact, dict) else getattr(fact, name, default)


def _mismatch(model: Model, ref: str, title: str, evidence: str, fix: Fix, clauses, assumptions=()) -> Finding:
    impact = model.price(fix)
    big = impact is not None and abs(impact) >= BIG_IMPACT
    return Finding(
        id="tender_mismatch",
        where=ref,
        severity="high" if big else "medium",
        title=title,
        evidence=evidence,
        impact_inr_per_kwh=impact,
        fix=fix,
        assumptions=tuple(assumptions),
        clauses=tuple(clauses),
    )


def _hours_mismatch(model: Model, fact: Any) -> list[Finding]:
    """The model counts a year differently from the way the RfS defines CUF."""
    if fact is None:
        return []
    want = float(_field(fact, "value"))
    clause = str(_field(fact, "clause", ""))
    for entry in model.structure["inputs"]:
        text = f"{entry.get('label') or ''} {entry.get('unit') or ''}".lower()
        value = entry["value"]
        if "hour" not in text and "hrs" not in text:
            continue
        if not isinstance(value, (int, float)) or value == want or not want * 0.5 <= value <= want * 1.5:
            continue
        fix = Fix(overrides={entry["cell"]: want}, note=f"The RfS defines the year as {want:,.0f} hours.")
        return [
            _mismatch(
                model,
                entry["cell"],
                f"The model uses {value:,.0f} hours a year, the RfS uses {want:,.0f}",
                f"{entry['cell']} holds {value:,.0f}; clause {clause} defines CUF on {want:,.0f} hours.",
                fix,
                clauses=(clause,) if clause else (),
            )
        ]
    return []


def _almm_mismatch(model: Model, facts: list[Any]) -> list[Finding]:
    """Modules priced as if the ALMM applied, when this tender exempts the project from it."""
    exempt = [f for f in facts if _field(f, "value")]
    if not exempt:
        return []
    clauses = tuple(sorted({str(_field(f, "clause", "")) for f in exempt if _field(f, "clause")}))
    inputs = {e["cell"]: e for e in model.structure["inputs"]}
    for ws in model.book.worksheets:
        for row in ws.iter_rows():
            note = next((c for c in row if isinstance(c.value, str) and "ALMM" in c.value.upper()), None)
            if note is None:
                continue
            priced = next((_ref(ws.title, c.coordinate) for c in row if _ref(ws.title, c.coordinate) in inputs), None)
            quote = MODULE_PRICE.search(note.value)
            if priced is None or quote is None:
                continue
            entry = inputs[priced]
            noted = float(quote.group(1))
            scale = float(entry["value"]) / noted
            fix = Fix(
                overrides={priced: ASSUMED_MODULE_PRICE_INR_PER_WP * scale},
                note=f"Re-price modules at INR {ASSUMED_MODULE_PRICE_INR_PER_WP:g}/Wp (A-03), the mock import quote.",
            )
            return [
                _mismatch(
                    model,
                    priced,
                    f"{entry['label'] or priced} are priced as ALMM-bound, but this tender exempts the project",
                    (
                        f"{priced} holds {_fmt(entry['value'])} {entry.get('unit') or ''}, "
                        f'noted as "{note.value.strip()}". '
                        f"Clauses {', '.join(clauses)} exempt the project from the ALMM, so imported modules apply. "
                        f"Priced at INR {ASSUMED_MODULE_PRICE_INR_PER_WP:g}/Wp per ASSUMPTIONS A-03."
                    ),
                    fix,
                    clauses=clauses,
                    assumptions=("A-03",),
                )
            ]
    return []


def tender_findings(model: Model, facts: list[Any]) -> list[Finding]:
    """Model-versus-tender checks, driven by the golden facts until Phase 2 extracts them for real."""
    by_field = {str(_field(f, "field")): f for f in facts}
    almm = [f for f in facts if str(_field(f, "field", "")).startswith("almm_exempt")]
    return _hours_mismatch(model, by_field.get("cuf_hours_per_year")) + _almm_mismatch(model, almm)


# ---------- formulas we cannot evaluate ----------


def unsupported_function_findings(model: Model) -> list[Finding]:
    """Say which function and which cell, rather than quietly returning a wrong number.

    The cell comes back as #NAME?. Everything that does not read it is still trustworthy, so the
    rest of the audit carries on and only the numbers that would depend on it are withheld.
    """
    return [
        Finding(
            id="unsupported_function",
            where=cells[0],
            severity="medium",
            title=f"{name} is not supported by our formula engine",
            evidence=(
                f"{name} is used in {len(cells)} cell(s): {', '.join(cells[:6])}"
                f"{' and others' if len(cells) > 6 else ''}. Those cells read #NAME? here, so any "
                f"number that depends on them is withheld rather than guessed."
            ),
        )
        for name, cells in sorted(model.unsupported.items())
    ]


def circular_reference_findings(model: Model) -> list[Finding]:
    """A loop we solved by iteration, so the reviewer knows the number came from repeating it."""
    return [
        Finding(
            id="circular_reference",
            where=cycle["cells"][0],
            severity="info",
            title="A circular reference, solved by repeating until it settled",
            evidence=cycle["text"] + " Excel calls this iterative calculation; we do the same.",
            impact_inr_per_kwh=0.0,
        )
        for cycle in model.cycle_report
    ]
