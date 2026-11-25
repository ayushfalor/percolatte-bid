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

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter

from .workbook_reader import formula_refs, sheet_extents

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


def _index_of(coord: str, across: bool) -> int:
    """Where a cell sits along its own line: the column when the run goes across, else the row."""
    row, col = coordinate_to_tuple(coord)
    return col if across else row


def _align_to_siblings(book, runs: list[Run]) -> list[Run]:
    """Stretch each run to the extent its neighbours use, picking up numbers at the ends.

    A run starts and ends at a formula, so a number pasted over the first or last period of a row
    falls outside it and is never seen. The other columns of the same table still run the full
    length, so their shared extent says where this one should start and stop. Only numeric cells
    are taken in, which keeps the year-zero column and the headers out.
    """
    grouped: dict[tuple[str, bool], list[Run]] = defaultdict(list)
    for run in runs:
        grouped[(run.sheet, run.across)].append(run)

    aligned: list[Run] = []
    for (sheet, across), group in grouped.items():
        ws = book[sheet]
        spans = Counter((_index_of(r.cells[0], across), _index_of(r.cells[-1], across)) for r in group)
        (first, last), count = spans.most_common(1)[0]
        for run in group:
            start, end = _index_of(run.cells[0], across), _index_of(run.cells[-1], across)
            if count < 2 or start < first or end > last or (start, end) == (first, last):
                aligned.append(run)
                continue
            line = run.line
            cells = []
            for i in range(first, last + 1):
                cell = ws.cell(row=line, column=i) if across else ws.cell(row=i, column=line)
                inside = start <= i <= end
                numeric = isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
                if inside or numeric:
                    cells.append(cell.coordinate)
            aligned.append(Run(run.sheet, across, run.line, run.origin, run.formula, tuple(cells)))
    return aligned


def formula_runs(path: str) -> list[Run]:
    """Every filled-across row and filled-down column in the workbook."""
    book = load_workbook(path, data_only=False)
    runs: list[Run] = []
    for ws in book.worksheets:
        for row in range(1, ws.max_row + 1):
            runs.extend(_runs_in_line(ws, True, row))
        for col in range(1, ws.max_column + 1):
            runs.extend(_runs_in_line(ws, False, col))
    return _align_to_siblings(book, runs)


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


def _signed_pair(formula: str, sheet: str, names: dict[str, str], value_of, extents=None) -> tuple[str, str] | None:
    """A formula that adds exactly two cells, one positive and one negative: (positive, negative)."""
    refs = [f"{s}!{c}" for s, c in formula_refs(formula, sheet, names, extents)]
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
    """A series that combines revenue with a cost, and the operator that joins them."""

    at: str  # the cell holding the combination
    position: tuple[int, int, int]  # sheet order, row, column, so margins can be read top down
    revenue: str  # the side that depends on the tariff
    cost: str  # the side that does not
    operator: str  # "+" when costs are stored negative, "-" when they are stored positive


def reads_graph(book, runs: list[Run]) -> dict[str, set[str]]:
    """Which cells each formula cell reads, over the whole workbook."""
    names = {name.upper(): dn.attr_text for name, dn in book.defined_names.items()}
    extents = sheet_extents(book)
    graph: dict[str, set[str]] = {}
    for ws in book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if not _is_formula(cell.value):
                    continue
                ref = f"{ws.title}!{cell.coordinate}"
                graph[ref] = {f"{s}!{c}" for s, c in formula_refs(cell.value, ws.title, names, extents)}
    return graph


def depends_on(graph: dict[str, set[str]], source: str) -> set[str]:
    """Every cell that reads `source`, directly or through any chain of formulas."""
    readers: dict[str, set[str]] = {}
    for ref, reads in graph.items():
        for read in reads:
            readers.setdefault(read, set()).add(ref)
    seen, queue = {source}, [source]
    while queue:
        for nxt in readers.get(queue.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def two_term_sum(formula: str, sheet: str) -> tuple[str, str, str] | None:
    """A formula that is exactly one cell plus or minus one other cell: (left, operator, right).

    A margin adds or subtracts. Revenue multiplies generation by a tariff, so insisting on a
    two-term sum keeps revenue itself from being mistaken for the margin.
    """
    try:
        tokens = [t for t in Tokenizer(formula).items if t.type != Token.WSPACE]
    except Exception:
        return None
    if len(tokens) != 3:
        return None
    left, middle, right = tokens
    if middle.type != Token.OP_IN or middle.value not in ("+", "-"):
        return None
    if any(t.type != Token.OPERAND or t.subtype != Token.RANGE or ":" in t.value for t in (left, right)):
        return None
    qualify = lambda v: v if "!" in v else f"{sheet}!{v}"  # noqa: E731
    return qualify(left.value.replace("$", "")), middle.value, qualify(right.value.replace("$", ""))


def operating_cost(path: str, runs: list[Run], tariff_ref: str) -> tuple[Run, str] | None:
    """The cost run an unwired operating cost belongs in, and the operator that charges it.

    Anchored on the tariff, because that is the one cell we can always identify. Revenue is what
    depends on the tariff; the operating margin is the first series that adds or subtracts a
    revenue series and a series that does not depend on the tariff. Tax, PAT and cash flow all
    depend on the tariff on both sides, so they do not qualify, and the operator tells us whether
    this model stores its costs as negative numbers or positive ones.
    """
    book = load_workbook(path, data_only=False)
    graph = reads_graph(book, runs)
    tariff_driven = depends_on(graph, tariff_ref)
    order = {name: i for i, name in enumerate(book.sheetnames)}
    by_ref = {ref: run for run in runs for ref in run.refs}

    margins: list[Margin] = []
    for run in runs:
        ws = book[run.sheet]
        for coord in run.cells:
            value = ws[coord].value
            if not _is_formula(value):
                continue
            parts = two_term_sum(value, run.sheet)
            if parts is None:
                continue
            left, operator, right = parts
            sides = [side for side in (left, right) if side in tariff_driven]
            if len(sides) != 1:
                continue
            cost = right if left in tariff_driven else left
            if cost in tariff_driven or cost not in by_ref:
                continue
            row, col = coordinate_to_tuple(coord)
            margins.append(Margin(f"{run.sheet}!{coord}", (order[run.sheet], row, col), sides[0], cost, operator))

    if not margins:
        return None
    first = min(margins, key=lambda margin: margin.position)
    return by_ref[first.cost], first.operator


def next_along(sheet: str, coord: str, across: bool) -> str:
    """The cell just past this one, along a row or down a column."""
    row, col = coordinate_to_tuple(coord)
    return f"{sheet}!{get_column_letter(col + 1)}{row}" if across else f"{sheet}!{get_column_letter(col)}{row + 1}"
