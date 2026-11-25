"""Template-free workbook evaluation.

Wraps the `formulas` library so the rest of the app can say
"set Inputs!C12 to 2.5, what is Returns!C8?" without knowing anything
about the workbook's layout. Nothing here assumes a sheet name or a cell.

Three jobs:
  evaluate()   recalculate with overrides (non-destructive, the file is never written)
  goal_seek()  find the input value that makes an output hit a target
  parity()     recompute every formula and compare with the values Excel saved,
               so we can prove our engine agrees with Excel before trusting it
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

os.environ.setdefault("TQDM_DISABLE", "1")  # formulas shows progress bars while loading; keep logs clean

import formulas
from openpyxl import load_workbook
from openpyxl.formula.tokenizer import Token, Tokenizer

from .workbook_reader import formula_refs, sheet_extents

_REF_RE = re.compile(r"^(?:'?(?P<sheet>[^!]+?)'?!)?\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d+)$")

CYCLE_MAX_ITERATIONS = 100
CYCLE_TOLERANCE = 0.001  # INR crore, or whatever the cycle's cells are measured in
CYCLE_MAX_CELLS = 12  # a bigger loop costs one recalculation per cell per pass; report it instead


class EngineError(ValueError):
    """Raised for bad references or values the caller can fix."""


@dataclass
class GoalSeekResult:
    value: float | None
    achieved: float | None
    iterations: int
    converged: bool
    elapsed_ms: int
    message: str = ""


@dataclass
class ParityReport:
    formula_cells: int
    compared: int
    matched: int
    no_cached_value: int
    mismatches: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.compared == 0:
            return "no_cached_values"
        return "match" if self.matched == self.compared else "mismatch"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "formula_cells": self.formula_cells,
            "compared": self.compared,
            "matched": self.matched,
            "no_cached_value": self.no_cached_value,
            "mismatches": self.mismatches[:25],
        }


def _plain(value: Any) -> Any:
    """Turn numpy / formulas values into JSON-friendly Python values."""
    if hasattr(value, "value"):  # formulas Ranges
        value = value.value
    if hasattr(value, "shape"):  # numpy array
        value = value.ravel()[0] if value.size else None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)  # Excel errors (#DIV/0!, #NUM!) come back as strings


def used_functions(path: str) -> dict[str, list[str]]:
    """Every worksheet function the workbook calls, and the cells that call it."""
    book = load_workbook(path, data_only=False)
    found: dict[str, list[str]] = {}
    for ws in book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                    continue
                try:
                    tokens = Tokenizer(cell.value).items
                except Exception:  # a formula we cannot tokenize tells us nothing about functions
                    continue
                for tok in tokens:
                    if tok.type == Token.FUNC and tok.subtype == Token.OPEN:
                        name = tok.value.rstrip("(").upper().lstrip("_XLFN.")
                        found.setdefault(name, []).append(f"{ws.title}!{cell.coordinate}")
    return found


def unsupported_functions(used: dict[str, list[str]]) -> dict[str, list[str]]:
    """Of those, the ones our formula library has no implementation for.

    Asked of the library's own registry rather than a list we keep by hand, so this stays right
    when the library gains a function.
    """
    known = set(formulas.get_functions())
    return {name: cells for name, cells in used.items() if name not in known}


def _strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan, written as a loop so a deep model cannot blow the Python stack."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0

    for root in graph:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(graph.get(root, ())))]
        while work:
            node, neighbours = work[-1]
            descended = False
            for nxt in neighbours:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(graph.get(nxt, ()))))
                    descended = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if descended:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    popped = stack.pop()
                    on_stack.discard(popped)
                    component.append(popped)
                    if popped == node:
                        break
                components.append(component)
    return components


def find_cycles(path: str) -> list[list[str]]:
    """Cells that depend on themselves, directly or round a loop.

    Excel calls this iterative calculation and solves it by repeating the sheet until it settles.
    Our formula library returns nothing for a cycle, so we have to find them before trusting it.
    """
    book = load_workbook(path, data_only=False)
    names = {name.upper(): dn.attr_text for name, dn in book.defined_names.items()}
    extents = sheet_extents(book)
    formulas_by_ref: dict[str, str] = {}
    for ws in book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formulas_by_ref[f"{ws.title}!{cell.coordinate}"] = cell.value

    graph: dict[str, set[str]] = {}
    for ref, formula in formulas_by_ref.items():
        sheet = ref.rsplit("!", 1)[0]
        reads = {f"{s}!{c}" for s, c in formula_refs(formula, sheet, names, extents)}
        graph[ref] = {r for r in reads if r in formulas_by_ref}

    cycles = [sorted(part) for part in _strongly_connected(graph) if len(part) > 1]
    cycles.extend([ref] for ref, reads in graph.items() if ref in reads)
    return sorted(cycles, key=len, reverse=True)


def describe_cycle(cycle: list[str]) -> str:
    """Plain English, so the finding reads like a sentence rather than a graph dump."""
    if len(cycle) == 1:
        return f"{cycle[0]} refers to itself."
    chain = ", which depends on ".join(cycle)
    return f"{chain}, which depends back on {cycle[0]}."


class WorkbookEngine:
    """One loaded workbook. Thread-safe; compile once, evaluate many times."""

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self.path = path
        self.book = os.path.basename(path)
        self._lock = threading.Lock()

        wb = load_workbook(path, data_only=False)
        self.sheet_names: list[str] = list(wb.sheetnames)
        self._sheet_lookup = {name.upper(): name for name in self.sheet_names}
        self.defined_names: dict[str, str] = {}
        for name, dn in wb.defined_names.items():
            self.defined_names[name] = dn.attr_text
        self.initial_values: dict[str, Any] = {}
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if c.value is not None:
                        self.initial_values[f"{ws.title}!{c.coordinate}"] = c.value

        self.functions_used = used_functions(path)
        self.unsupported = unsupported_functions(self.functions_used)
        self.cycles = find_cycles(path)
        self.cycle_report = [{"cells": cycle, "text": describe_cycle(cycle)} for cycle in self.cycles]
        self._cycle_cells = [c for cycle in self.cycles if len(cycle) <= CYCLE_MAX_CELLS for c in cycle]
        self._cycle_base: dict[str, Any] | None = None

        t0 = time.perf_counter()
        self._model = formulas.ExcelModel().loads(path).finish(circular=bool(self.cycles))
        self._base = self._model.calculate()
        self.compile_ms = int((time.perf_counter() - t0) * 1000)
        self._key_lookup = {k.upper(): k for k in self._base}

    # ---------- references ----------
    def normalize_ref(self, ref: str) -> str:
        """'Tariff' -> 'Inputs!C12', "'My Sheet'!$b$4" -> 'My Sheet!B4'."""
        ref = ref.strip()
        for name, target in self.defined_names.items():
            if name.upper() == ref.upper():
                if ":" in target or "," in target:
                    raise EngineError(f"Named range '{ref}' covers several cells ({target}); pass one cell")
                ref = target
                break
        m = _REF_RE.match(ref.replace("$", ""))
        if not m or not m.group("sheet"):
            raise EngineError(f"Use a sheet-qualified single cell like Inputs!C12 (got '{ref}')")
        sheet = self._sheet_lookup.get(m.group("sheet").strip("'").upper())
        if sheet is None:
            raise EngineError(f"No sheet named '{m.group('sheet')}'. Sheets: {', '.join(self.sheet_names)}")
        return f"{sheet}!{m.group('col').upper()}{m.group('row')}"

    def _key(self, ref: str) -> str:
        sheet, cell = self.normalize_ref(ref).split("!")
        guess = f"'[{self.book}]{sheet.upper()}'!{cell}".upper()
        key = self._key_lookup.get(guess)
        if key is None:
            # Constant cells nobody references may be missing from the graph; build the key anyway.
            key = f"'[{self.book}]{sheet.upper()}'!{cell}"
        return key

    def current_value(self, ref: str) -> Any:
        norm = self.normalize_ref(ref)
        if self._cycle_cells:
            if self._cycle_base is None:
                self._cycle_base = self._solve_cycles({})
            if norm in self._cycle_base:
                return self._cycle_base[norm]
        key = self._key_lookup.get(self._key(norm).upper())
        if key is not None:
            return _plain(self._base[key])
        return self.initial_values.get(norm)

    # ---------- evaluation ----------
    def evaluate(self, overrides: dict[str, Any] | None = None, outputs: list[str] | None = None) -> dict[str, Any]:
        overrides = dict(overrides or {})
        if self._cycle_cells:
            # The caller's own overrides win: they may be pinning a cell inside the loop.
            overrides = {**self._solve_cycles(overrides), **overrides}
        return self._evaluate_once(overrides, outputs)

    def _solve_cycles(self, overrides: dict[str, Any]) -> dict[str, Any]:
        """Repeat the loop until it stops moving, the way Excel's iterative calculation does.

        One recalculation per cell per pass: a cell's own formula can only be worked out when the
        other cells in its loop are pinned to the current guess.
        """
        pinned = {self.normalize_ref(ref) for ref in overrides}
        unknown = [cell for cell in self._cycle_cells if cell not in pinned]
        if not unknown:
            return {}
        guess: dict[str, Any] = dict.fromkeys(unknown, 0.0)
        for _ in range(CYCLE_MAX_ITERATIONS):
            worst = 0.0
            for cell in unknown:
                others = {k: v for k, v in guess.items() if k != cell}
                value = self._evaluate_once({**overrides, **others}, [cell]).get(cell)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                worst = max(worst, abs(float(value) - float(guess[cell])))
                guess[cell] = float(value)
            if worst < CYCLE_TOLERANCE:
                break
        return guess

    def _evaluate_once(
        self, overrides: dict[str, Any] | None = None, outputs: list[str] | None = None
    ) -> dict[str, Any]:
        overrides = overrides or {}
        outputs = outputs or []
        if not outputs:
            raise EngineError("Ask for at least one output cell")
        inputs = {self._key(r): v for r, v in overrides.items()}
        out_keys = {self._key(o): self.normalize_ref(o) for o in outputs}
        with self._lock:
            sol = self._model.calculate(inputs=inputs, outputs=list(out_keys)) if inputs else self._base
        result: dict[str, Any] = {}
        for key, norm in out_keys.items():
            found = sol.get(key)
            if found is None:
                found_key = self._key_lookup.get(key.upper())
                found = sol.get(found_key) if found_key else None
            result[norm] = _plain(found) if found is not None else self.initial_values.get(norm)
        return result

    def goal_seek(
        self,
        variable: str,
        target: str,
        target_value: float,
        lower: float | None = None,
        upper: float | None = None,
        tolerance: float = 1e-7,
        max_iter: int = 60,
        overrides: dict[str, Any] | None = None,
    ) -> GoalSeekResult:
        """Bracket, then Illinois regula falsi. Typically 6-12 recalcs."""
        t0 = time.perf_counter()
        overrides = dict(overrides or {})
        var = self.normalize_ref(variable)
        tgt = self.normalize_ref(target)
        calls = 0

        def f(x: float) -> float | None:
            nonlocal calls
            calls += 1
            got = self.evaluate({**overrides, var: x}, [tgt])[tgt]
            return (got - target_value) if isinstance(got, (int, float)) else None

        start = overrides.get(var, self.current_value(var))
        if not isinstance(start, (int, float)):
            raise EngineError(f"{var} is not numeric, can't goal seek on it")
        start = float(start)

        lo, hi = lower, upper
        if lo is None or hi is None:
            step = max(abs(start) * 0.05, 0.01)
            lo, hi = start - step, start + step
            for _ in range(25):
                flo, fhi = f(lo), f(hi)
                if flo is not None and fhi is not None and flo * fhi <= 0:
                    break
                step *= 2
                lo, hi = start - step, start + step
        flo, fhi = f(lo), f(hi)
        if flo is None or fhi is None or flo * fhi > 0:
            return GoalSeekResult(
                None,
                None,
                calls,
                False,
                int((time.perf_counter() - t0) * 1000),
                f"Could not bracket a solution for {tgt} = {target_value} by moving {var}",
            )

        side = 0
        x = lo
        for _ in range(max_iter):
            x = (lo * fhi - hi * flo) / (fhi - flo)
            fx = f(x)
            if fx is None:
                x = (lo + hi) / 2
                fx = f(x)
                if fx is None:
                    break
            if abs(fx) < tolerance or abs(hi - lo) < 1e-12:
                achieved = fx + target_value
                return GoalSeekResult(x, achieved, calls, True, int((time.perf_counter() - t0) * 1000))
            if fx * fhi > 0:
                hi, fhi = x, fx
                if side == -1:
                    flo /= 2
                side = -1
            else:
                lo, flo = x, fx
                if side == 1:
                    fhi /= 2
                side = 1
        return GoalSeekResult(
            x, None, calls, False, int((time.perf_counter() - t0) * 1000), "Did not converge within the iteration limit"
        )

    # ---------- trust check ----------
    def parity(self, rel_tol: float = 1e-9, abs_tol: float = 1e-9) -> ParityReport:
        """Recompute every formula and compare with Excel's cached values."""
        wbf = load_workbook(self.path, data_only=False)
        wbv = load_workbook(self.path, data_only=True)
        report = ParityReport(0, 0, 0, 0)
        for ws in wbf.worksheets:
            cached_ws = wbv[ws.title]
            for row in ws.iter_rows():
                for c in row:
                    if not (isinstance(c.value, str) and c.value.startswith("=")):
                        continue
                    report.formula_cells += 1
                    cached = cached_ws[c.coordinate].value
                    if cached is None:
                        report.no_cached_value += 1
                        continue
                    ref = f"{ws.title}!{c.coordinate}"
                    key = self._key_lookup.get(self._key(ref).upper())
                    computed = _plain(self._base[key]) if key else None
                    report.compared += 1
                    same = (
                        math.isclose(float(computed), float(cached), rel_tol=rel_tol, abs_tol=abs_tol)
                        if isinstance(computed, (int, float)) and isinstance(cached, (int, float))
                        else (computed in (None, "") and cached in (None, "")) or computed == cached
                    )
                    if same:
                        report.matched += 1
                    else:
                        report.mismatches.append({"cell": ref, "formula": c.value, "excel": cached, "engine": computed})
        return report


_CACHE: dict[str, WorkbookEngine] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 8


def get_engine(path: str) -> WorkbookEngine:
    """Compile once per file (about 2 s), then reuse."""
    with _CACHE_LOCK:
        eng = _CACHE.get(path)
        if eng is None:
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.pop(next(iter(_CACHE)))
            eng = WorkbookEngine(path)
            _CACHE[path] = eng
        return eng
