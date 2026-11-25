"""Template-free workbook structure: sheets, names, labels, units and the reference graph.

This is the Reader agent's deterministic core. It never assumes a layout:
labels come from the nearest text to the left of a cell, and a cell's role
(input, calculation, unused number) comes from the reference graph.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from itertools import pairwise
from typing import Any

from openpyxl import load_workbook
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.utils.cell import get_column_letter, range_boundaries

LEGACY_NAME = re.compile(r"(old|backup|copy|archive|superseded|deprecated|_v\d|\bv\d)", re.I)
MAX_RANGE_CELLS = 20000


def _split_ref(ref: str, current_sheet: str) -> tuple[str, str]:
    if "!" in ref:
        sheet, addr = ref.rsplit("!", 1)
        return sheet.strip("'").replace("''", "'"), addr
    return current_sheet, ref


def _expand(addr: str) -> list[str]:
    addr = addr.replace("$", "")
    try:
        min_col, min_row, max_col, max_row = range_boundaries(addr)
    except ValueError:
        return []
    if None in (min_col, min_row, max_col, max_row):
        return []  # whole-row / whole-column references: skip cell expansion
    if (max_col - min_col + 1) * (max_row - min_row + 1) > MAX_RANGE_CELLS:
        return []
    return [f"{get_column_letter(c)}{r}" for r in range(min_row, max_row + 1) for c in range(min_col, max_col + 1)]


def formula_refs(formula: str, sheet: str, names: dict[str, str]) -> list[tuple[str, str]]:
    """All (sheet, cell) pairs a formula reads, with named ranges resolved."""
    out: list[tuple[str, str]] = []
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return out
    for tok in tokens:
        if tok.type != Token.OPERAND or tok.subtype != Token.RANGE:
            continue
        value = tok.value
        target = names.get(value.upper())
        if target:
            value = target
        s, addr = _split_ref(value, sheet)
        out.extend((s, cell) for cell in _expand(addr))
    return out


def _label_left(ws, row: int, col: int) -> str | None:
    """The row's caption: the leftmost text on the row, left of this cell.

    Leftmost, not nearest, because models keep captions in a first column and put qualifiers
    in between. Scanning back from the cell gives Capex!D5 the basis "per MWp"; the caption
    column gives it "PV modules", which is what the cell is actually called.
    """
    for c in range(1, col):
        v = ws.cell(row=row, column=c).value
        if isinstance(v, str) and v.strip() and not v.startswith("="):
            return v.strip()
    return None


def _label_above(ws, row: int, col: int) -> str | None:
    """The nearest text above a cell in its own column: a table's column header."""
    for r in range(row - 1, 0, -1):
        v = ws.cell(row=r, column=col).value
        if isinstance(v, str) and v.strip() and not v.startswith("="):
            return v.strip()
    return None


def _unit_right(ws, row: int, col: int) -> str | None:
    v = ws.cell(row=row, column=col + 1).value
    if isinstance(v, str) and 0 < len(v.strip()) <= 24 and not v.startswith("="):
        return v.strip()
    return None


def _is_axis(values: list[Any]) -> bool:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(nums) < 3 or any(float(n) != int(n) for n in nums):
        return False
    diffs = {int(b) - int(a) for a, b in pairwise(nums)}
    return diffs == {1}


def _name_of(ws, cell, row_numbers: list[Any]) -> tuple[str | None, str]:
    """What this cell is called, and where the name came from.

    A parameter list has one number per row, so the text to its left names it ("Interest rate").
    A table of records has several numbers on a row, so the row text is the record's name and the
    column header is what names the cell: Scenarios!D5 is the CUF of the "Base" scenario, and the
    useful label is "CUF (AC)", not "Base".
    """
    left = _label_left(ws, cell.row, cell.column)
    above = _label_above(ws, cell.row, cell.column)
    is_record_row = len(row_numbers) > 1 and not _is_axis(row_numbers)
    if is_record_row and above:
        return above, "column"
    return (left, "row") if left else (above, "column")


def read_structure(path: str) -> dict[str, Any]:
    wbf = load_workbook(path, data_only=False)
    names = {name.upper(): dn.attr_text for name, dn in wbf.defined_names.items()}

    sheets: list[dict[str, Any]] = []
    refs_into: dict[tuple[str, str], int] = Counter()
    sheet_links: Counter = Counter()
    formula_count = 0
    numbers: list[tuple[str, str]] = []
    comments: list[dict[str, str]] = []

    for ws in wbf.worksheets:
        stats = Counter()
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if c.comment:
                    comments.append({"cell": f"{ws.title}!{c.coordinate}", "text": c.comment.text.strip()})
                if v is None:
                    continue
                if isinstance(v, str) and v.startswith("="):
                    stats["formulas"] += 1
                    formula_count += 1
                    for s, cell in formula_refs(v, ws.title, names):
                        refs_into[(s, cell)] += 1
                        if s != ws.title:
                            sheet_links[(ws.title, s)] += 1
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    stats["numbers"] += 1
                    numbers.append((ws.title, c.coordinate))
                elif isinstance(v, str):
                    stats["text"] += 1
        sheets.append(
            {
                "name": ws.title,
                "state": ws.sheet_state,
                "dimensions": ws.dimensions,
                "formulas": stats["formulas"],
                "numbers": stats["numbers"],
                "text": stats["text"],
                "merged_ranges": len(ws.merged_cells.ranges),
            }
        )

    incoming = Counter(dst for (_, dst) in sheet_links.elements())
    outgoing = Counter(src for (src, _) in sheet_links.elements())
    for s in sheets:
        s["referenced_by_other_sheets"] = incoming.get(s["name"], 0)
        s["references_other_sheets"] = outgoing.get(s["name"], 0)
        isolated = s["referenced_by_other_sheets"] == 0 and s["references_other_sheets"] == 0 and s["formulas"] == 0
        if not isolated:
            s["role"] = "model"
        elif s["numbers"] > 0:
            s["role"] = "legacy_candidate"
            s["why"] = "Holds numbers but nothing reads them and it reads nothing"
            if s["state"] != "visible" or LEGACY_NAME.search(s["name"]):
                s["why"] += "; hidden or named like an old copy"
        else:
            s["role"] = "documentation"

    live = {s["name"] for s in sheets if s["role"] == "model"}
    inputs, unused = [], []
    by_row: dict[tuple[str, int], list[Any]] = defaultdict(list)
    by_col: dict[tuple[str, int], list[Any]] = defaultdict(list)
    for sheet, coord in numbers:
        cell = wbf[sheet][coord]
        by_row[(sheet, cell.row)].append(cell.value)
        by_col[(sheet, cell.column)].append(cell.value)
    for sheet, coord in numbers:
        ws = wbf[sheet]
        cell = ws[coord]
        label, label_source = _name_of(ws, cell, by_row[(sheet, cell.row)])
        on_axis = _is_axis(by_row[(sheet, cell.row)]) or _is_axis(by_col[(sheet, cell.column)])
        entry = {
            "cell": f"{sheet}!{coord}",
            "value": cell.value,
            "label": label,
            "label_source": label_source,
            "unit": _unit_right(ws, cell.row, cell.column),
            "number_format": cell.number_format,
            "dependents": refs_into.get((sheet, coord), 0),
            "axis": on_axis,
        }
        if cell.comment:
            entry["comment"] = cell.comment.text.strip()
        if entry["dependents"] > 0:
            inputs.append(entry)
        elif sheet in live and not on_axis:
            unused.append(entry)

    inputs.sort(key=lambda e: -e["dependents"])
    return {
        "kind": "workbook",
        "sheets": sheets,
        "defined_names": {name: dn.attr_text for name, dn in wbf.defined_names.items()},
        "totals": {
            "sheets": len(sheets),
            "formulas": formula_count,
            "numbers": len(numbers),
            "comments": len(comments),
        },
        "sheet_links": [{"from": a, "to": b, "references": n} for (a, b), n in sorted(sheet_links.items())],
        "inputs": inputs,
        "unreferenced_numbers": unused,
        "comments": comments,
    }


def label_for(book, ref: str) -> str | None:
    """What one cell is called, on an already-loaded workbook. Same rule as read_structure."""
    sheet, coord = ref.rsplit("!", 1)
    ws = book[sheet]
    cell = ws[coord]
    row_numbers = [c.value for c in ws[cell.row] if isinstance(c.value, (int, float)) and not isinstance(c.value, bool)]
    return _name_of(ws, cell, row_numbers)[0]


def key_cells(path: str, defined_names: dict[str, str] | None = None) -> dict[str, str | None]:
    """The three cells every module needs: the tariff input, equity IRR and minimum DSCR.

    Found by label, so a workbook we have never seen resolves the same way the sample does.
    A defined name called Tariff wins, because that is what the model's own formulas use.
    """
    named_tariff = any(name.upper() == "TARIFF" for name in (defined_names or {}))
    return {
        "tariff": "Tariff" if named_tariff else find_by_label({}, [r"^tariff"], path),
        "equity_irr": find_by_label({}, [r"equity irr"], path),
        "min_dscr": find_by_label({}, [r"min(imum)? dscr"], path),
    }


def find_by_label(structure: dict[str, Any], patterns: list[str], wb_path: str) -> str | None:
    """First cell whose left label matches any pattern (case-insensitive). Used for defaults only."""
    wb = load_workbook(wb_path, data_only=False)
    regs = [re.compile(p, re.I) for p in patterns]
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and any(r.search(c.value) for r in regs) and not c.value.startswith("="):
                    for col in range(c.column + 1, min(c.column + 4, ws.max_column + 1)):
                        target = ws.cell(row=c.row, column=col)
                        is_plain_text = isinstance(target.value, str) and not target.value.startswith("=")
                        if target.value is not None and not is_plain_text:
                            return f"{ws.title}!{target.coordinate}"
    return None
