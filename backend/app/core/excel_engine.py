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

import formulas  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

_REF_RE = re.compile(r"^(?:'?(?P<sheet>[^!]+?)'?!)?\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d+)$")


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

        t0 = time.perf_counter()
        self._model = formulas.ExcelModel().loads(path).finish()
        self._base = self._model.calculate()
        self.compile_ms = int((time.perf_counter() - t0) * 1000)
        self._key_lookup = {k.upper(): k for k in self._base.keys()}

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
        key = self._key_lookup.get(self._key(norm).upper())
        if key is not None:
            return _plain(self._base[key])
        return self.initial_values.get(norm)

    # ---------- evaluation ----------
    def evaluate(self, overrides: dict[str, Any] | None = None, outputs: list[str] | None = None) -> dict[str, Any]:
        overrides = overrides or {}
        outputs = outputs or []
        if not outputs:
            raise EngineError("Ask for at least one output cell")
        inputs = {self._key(r): v for r, v in overrides.items()}
        out_keys = {self._key(o): self.normalize_ref(o) for o in outputs}
        with self._lock:
            if inputs:
                sol = self._model.calculate(inputs=inputs, outputs=list(out_keys))
            else:
                sol = self._base
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
            return GoalSeekResult(None, None, calls, False, int((time.perf_counter() - t0) * 1000),
                                  f"Could not bracket a solution for {tgt} = {target_value} by moving {var}")

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
        return GoalSeekResult(x, None, calls, False, int((time.perf_counter() - t0) * 1000),
                              "Did not converge within the iteration limit")

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
