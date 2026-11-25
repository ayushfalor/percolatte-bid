"""Apply a fix to a copy of a workbook, never to the workbook itself (D-010).

Value overrides go straight to the engine, which already recalculates without writing
anything. Formula patches cannot: they change the shape of the model, so they need a real
file. We copy the workbook into a temp directory, patch the copy and compile that.

Compiling costs about two seconds, so engines are cached by file hash plus the patch set.
A test session that applies the same fix twice pays for it once.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import shutil
import tempfile
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .contracts import Fix
from .excel_engine import WorkbookEngine, get_engine

CURRENT = "{current}"  # in an append template, stands for whatever the cell holds now
_CACHE_MAX = 12
_cache: dict[str, WorkbookEngine] = {}
_lock = threading.Lock()
_temp_root: str | None = None


def _root() -> str:
    """One temp directory per process, removed on exit."""
    global _temp_root
    if _temp_root is None:
        _temp_root = tempfile.mkdtemp(prefix="bid-workbench-patched-")
        atexit.register(shutil.rmtree, _temp_root, ignore_errors=True)
    return _temp_root


def file_hash(path: str) -> str:
    """Identifies the file itself, so a cache key never survives the file changing."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def fold(templates: list[str]) -> str:
    """Several patches aimed at one cell, folded into a single template.

    Replaces land first, then each append wraps what is already there. Without this a fix that
    restores a cell's formula would quietly discard a term another fix added to the same cell,
    which is exactly what happens to the year-6 O&M cell when insurance is wired at the same time.
    """
    replaces = [t for t in templates if CURRENT not in t]
    appends = [t for t in templates if CURRENT in t]
    folded = replaces[-1] if replaces else CURRENT
    for template in appends:
        folded = template.replace(CURRENT, folded)
    return folded


def merge(fixes: list[Fix]) -> tuple[dict[str, Any], dict[str, str]]:
    """Overrides and formula patches from several fixes, as one pair."""
    overrides: dict[str, Any] = {}
    stacked: dict[str, list[str]] = defaultdict(list)
    for fix in fixes:
        overrides.update(fix.overrides)
        for ref, template in fix.formula_patches.items():
            stacked[ref].append(template)
    return overrides, {ref: fold(templates) for ref, templates in stacked.items()}


def write_patched_copy(src: str, dst: str, patches: dict[str, str]) -> None:
    """Copy `src` to `dst` and patch the copy. `src` is only ever read.

    Templates never carry the leading "=", which this adds. A template holding `{current}`
    expands it to whatever the cell holds now. `merge` has already folded any patches that
    aim at the same cell, so each cell is written exactly once.
    """
    shutil.copyfile(src, dst)
    if not patches:
        return
    book = load_workbook(dst, data_only=False)
    for ref, template in patches.items():
        sheet, cell = ref.rsplit("!", 1)
        body = template
        if CURRENT in template:
            value = book[sheet][cell].value
            current = value[1:] if isinstance(value, str) and value.startswith("=") else f"{value}"
            body = template.replace(CURRENT, current)
        book[sheet][cell] = "=" + body
    book.save(dst)


def engine_for(path: str, patches: dict[str, str] | None = None) -> WorkbookEngine:
    """The compiled engine for this workbook with these formula patches applied.

    With no patches this is the shared engine for the file itself, so nothing is copied.
    """
    if not patches:
        return get_engine(path)
    key = f"{file_hash(path)}:{json.dumps(patches, sort_keys=True)}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    with _lock:
        cached = _cache.get(digest)
        if cached is not None:
            return cached
        copy = str(Path(_root()) / f"{digest}{Path(path).suffix}")
        write_patched_copy(path, copy, patches)
        engine = WorkbookEngine(copy)
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[digest] = engine
        return engine
