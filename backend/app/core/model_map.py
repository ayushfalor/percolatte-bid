"""The shape of a financial model, worked out from the workbook itself.

Nothing here knows a sheet name or a cell address. A model is read as runs: a line of cells
along a row or a column that all hold the same formula, written once and filled across. That
one idea answers most of what the Auditor needs to ask.

  - A number sitting inside a run is a value someone typed over a formula.
  - A cell that belongs to no run is a scalar, so it can be a total rather than one year of a
    series.
  - The operating cost series is the run that is added to the revenue run to make a margin,
    which is how an unwired cost finds the row it belongs in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter

from .workbook_reader import formula_refs

MIN_RUN = 4  # fewer cells than this is not a filled-across row, it is a coincidence


@dataclass(frozen=True)
class Run:
    """A line of cells that share one formula, filled along a row or down a column."""

    sheet: str
    across: bool  # True when the run goes along a row, False when it goes down a column
    line: int  # the row number when across, the column number when not
    origin: str  # coordinate of the first cell holding the shared formula
    formula: str  # that cell's formula
    cells: tuple[str, ...]  # every coordinate in the span, including any typed over

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(f"{self.sheet}!{c}" for c in self.cells)

    def formula_at(self, coord: str) -> str:
        """The shared formula as it should read in this cell."""
        return Translator(self.formula, origin=self.origin).translate_formula(coord)


def _line_cells(ws, across: bool, line: int) -> list[Any]:
    if across:
        return [ws.cell(row=line, column=c) for c in range(1, ws.max_column + 1)]
    return [ws.cell(row=r, column=line) for r in range(1, ws.max_row + 1)]


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _runs_in_line(ws, across: bool, line: int) -> list[Run]:
    """Maximal spans of cells whose formulas are translations of one another.

    A gap or a typed-over number does not end a span, which is the whole point: the span has to
    reach across the cell someone pasted a value into. Text ends it, because that is a new block.
    """
    cells = _line_cells(ws, across, line)
    runs: list[Run] = []
    start = 0
    while start < len(cells):
        head = cells[start]
        if not _is_formula(head.value):
            start += 1
            continue
        translator = Translator(head.value, origin=head.coordinate)
        last_match = start
        for offset in range(start + 1, len(cells)):
            cell = cells[offset]
            if cell.value is None or (isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)):
                continue
            if not _is_formula(cell.value):
                break
            try:
                same = cell.value == translator.translate_formula(cell.coordinate)
            except Exception:
                same = False
            if not same:
                break
            last_match = offset
        span = cells[start : last_match + 1]
        if sum(1 for c in span if _is_formula(c.value)) >= MIN_RUN:
            runs.append(Run(ws.title, across, line, head.coordinate, head.value, tuple(c.coordinate for c in span)))
        start = last_match + 1 if last_match > start else start + 1
    return runs


def formula_runs(path: str) -> list[Run]:
    """Every filled-across row and filled-down column in the workbook."""
    book = load_workbook(path, data_only=False)
    runs: list[Run] = []
    for ws in book.worksheets:
        for row in range(1, ws.max_row + 1):
            runs.extend(_runs_in_line(ws, True, row))
        for col in range(1, ws.max_column + 1):
            runs.extend(_runs_in_line(ws, False, col))
    return runs


def typed_over(path: str, runs: list[Run]) -> list[tuple[Run, str]]:
    """Cells holding a number where their run says there should be a formula."""
    book = load_workbook(path, data_only=False)
    out: list[tuple[Run, str]] = []
    for run in runs:
        ws = book[run.sheet]
        for coord in run.cells:
            value = ws[coord].value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append((run, coord))
    return out


def scalars(runs: list[Run]) -> set[str]:
    """Every cell that belongs to a run, so a caller can tell a total from one year of a series."""
    return {ref for run in runs for ref in run.refs}


def _signed_pair(formula: str, sheet: str, names: dict[str, str], value_of) -> tuple[str, str] | None:
    """A formula that adds exactly two cells, one positive and one negative: (positive, negative)."""
    refs = [f"{s}!{c}" for s, c in formula_refs(formula, sheet, names)]
    if len(refs) != 2:
        return None
    first, second = (value_of(ref) for ref in refs)
    if not isinstance(first, (int, float)) or not isinstance(second, (int, float)):
        return None
    if first > 0 > second:
        return refs[0], refs[1]
    if second > 0 > first:
        return refs[1], refs[0]
    return None


@dataclass(frozen=True)
class Margin:
    """A cell that adds one positive series to one negative series."""

    at: str  # the cell holding the sum
    position: tuple[int, int, int]  # sheet order, row, column, so margins can be read top down
    positive: str
    negative: str


def _margins(book, runs: list[Run], value_of) -> list[Margin]:
    names = {name.upper(): dn.attr_text for name, dn in book.defined_names.items()}
    order = {name: i for i, name in enumerate(book.sheetnames)}
    found: list[Margin] = []
    for run in runs:
        ws = book[run.sheet]
        for coord in run.cells:
            value = ws[coord].value
            if not _is_formula(value):
                continue
            pair = _signed_pair(value, run.sheet, names, value_of)
            if pair is None:
                continue
            row, col = coordinate_to_tuple(coord)
            found.append(Margin(f"{run.sheet}!{coord}", (order[run.sheet], row, col), pair[0], pair[1]))
    return found


def cost_series(path: str, runs: list[Run], value_of) -> Run | None:
    """The operating cost run: the row an unwired operating cost belongs in.

    A cash flow statement is full of cells that add a positive series to a negative one. On the
    sample, EBITDA, PAT, CFADS and project cash flow all qualify, and three of the four point at
    tax rather than at O&M. The one we want is the first margin: the earliest place in the model
    where revenue meets a cost, where the positive side is not itself already a margin.

    Finding it this way lets an unwired cost be charged in the right row on a workbook we have
    never seen, without knowing that the row happens to be called O&M.
    """
    book = load_workbook(path, data_only=False)
    by_ref = {ref: run for run in runs for ref in run.refs}
    margins = _margins(book, runs, value_of)
    derived = {margin.at for margin in margins}
    operating = [margin for margin in margins if margin.positive not in derived]
    if not operating:
        return None
    return by_ref.get(min(operating, key=lambda margin: margin.position).negative)


def next_along(sheet: str, coord: str, across: bool) -> str:
    """The cell just past this one, along a row or down a column."""
    row, col = coordinate_to_tuple(coord)
    return f"{sheet}!{get_column_letter(col + 1)}{row}" if across else f"{sheet}!{get_column_letter(col)}{row + 1}"
