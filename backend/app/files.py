"""File helpers: detect what a file is, and give agents a path on local disk."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from openpyxl import load_workbook

from .config import get_settings

ALLOWED = {".xlsx": "excel", ".xlsm": "excel", ".pdf": "pdf"}
SOLAR_WORDS = ("solar", "module", "irradia", "inverter", "/wp", "wp)", "ghi", "dc capacity", "pv ")
WIND_WORDS = ("wind", "turbine", "wtg", "hub height", "rotor")
MAX_TEXT_CELLS = 4000  # enough to see every label; the whole sheet would be slow on a big model


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def detect_kind(filename: str, content: bytes) -> str:
    """workbook (a bid model), history (auction results) or tender (a PDF)."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError(f"Unsupported file type '{ext}'. Upload .xlsx, .xlsm or .pdf")
    if ext == ".pdf":
        return "tender"
    path = materialize(sha256(content), ext, content)
    wb = load_workbook(path, read_only=True)
    names = {n.lower() for n in wb.sheetnames}
    wb.close()
    lowered = filename.lower()
    if {"tenders", "bids"} <= names or "auction" in lowered or "history" in lowered:
        return "history"
    return "workbook"


def materialize(sha: str, ext: str, content: bytes | None = None) -> str:
    """Write the bytes to a stable temp path named by hash (safe for formula engines)."""
    work = Path(get_settings().work_dir)
    work.mkdir(parents=True, exist_ok=True)
    path = work / f"{sha[:16]}{ext}"
    if not path.exists():
        if content is None:
            raise FileNotFoundError(path)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(content)
        os.replace(tmp, path)
    return str(path)


def detect_technology(path: str) -> str:
    """solar, wind or renewable, from the words in the model's own labels. Never from the file name."""
    wb = load_workbook(path, read_only=True)
    seen, solar, wind = 0, 0, 0
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if not isinstance(cell, str):
                    continue
                text = cell.lower()
                solar += sum(w in text for w in SOLAR_WORDS)
                wind += sum(w in text for w in WIND_WORDS)
                seen += 1
                if seen >= MAX_TEXT_CELLS:
                    break
            if seen >= MAX_TEXT_CELLS:
                break
    wb.close()
    if solar == wind:
        return "renewable"
    return "solar" if solar > wind else "wind"
