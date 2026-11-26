"""Phase 5: what a what-if means, worked out from the workbook, with no model in the loop.

The Copilot has to run with no API key, so the common levers are understood by rule: which input
the sentence is about (by label, the same way the Auditor finds cells), how much it moves, and in
the cell's own unit. A cell that stores 9.25 for 9.25% moves by 0.5 for 50 basis points; one that
stores 0.095 moves by 0.005. Numbers always come from the workbook; the model, when there is one,
only words the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook

from .checks import MODULE_PRICE
from .workbook_reader import key_cells, read_structure

# What people call the inputs. Each row lists the words a sentence might use for one lever.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "interest": ("interest", "cost of debt", "debt cost", "lending rate", "loan rate"),
    "cuf": ("cuf", "plf", "capacity utilisation", "capacity utilization", "plant load"),
    "capex": ("capex", "investment", "project cost", "capital cost"),
    "module": ("module", "modules", "panel", "panels"),
    "om": ("o&m", "o & m", "opex", "operating expense", "operating cost", "maintenance"),
    "debt_share": ("debt share", "gearing", "leverage", "debt ratio", "debt to equity"),
    "tariff": ("tariff", "bid", "price per kwh"),
    "degradation": ("degradation",),
    "tenor": ("tenor", "loan term", "repayment period"),
    "tax": ("tax rate", "tax"),
    "capacity": ("capacity", "mw"),
}
UP = re.compile(r"\b(rise|rises|rising|increase|increases|up|higher|more|grow|grows|add)\b", re.I)
DOWN = re.compile(
    r"\b(fall|falls|falling|drop|drops|decrease|decreases|down|lower|less|cut|cuts|reduce|reduces)\b", re.I
)
BASIS_POINTS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bp|bps|basis points?)\b", re.I)
RELATIVE_PERCENT = re.compile(r"\bby\s+(\d+(?:\.\d+)?)\s*%", re.I)
SET_PERCENT = re.compile(r"\b(?:is|to|at|of|=)\s+(\d+(?:\.\d+)?)\s*%", re.I)
PER_WP = re.compile(r"(?:INR|₹|Rs\.?)?\s*(\d+(?:\.\d+)?)\s*/\s*Wp\b", re.I)
SET_NUMBER = re.compile(r"\b(?:is|to|at|=|bid|bids|bidding)\s+(?:INR|₹|Rs\.?)?\s*(\d+(?:\.\d+)?)\b", re.I)
RIVAL_WORDS = re.compile(
    r"\b(rival|rivals|competitor|competitors|bidder|bidders|field|snapshot|renew|adani|jsw|tata|avaada|acme)\b", re.I
)
EDIT_WORDS = re.compile(
    r"\b(make|set|assume|suppose|more|less|aggressive|won't|will not|remove|drop|change|cut|raise)\b", re.I
)
WHOLE_NUMBER_PERCENT = 1.0  # a percent input above this is stored as 9.25, not 0.0925


@dataclass(frozen=True)
class WhatIf:
    cell: str  # the input the sentence is about, e.g. "Inputs!C21"
    label: str  # what the workbook calls it
    before: float
    after: float
    phrase: str  # the part of the message that named the change, for the scenario's name


def _lever(message: str) -> str | None:
    text = message.lower()
    hits = [(len(word), key) for key, words in SYNONYMS.items() for word in words if word in text]
    return max(hits)[1] if hits else None


def _inputs(path: str) -> list[dict[str, Any]]:
    """Numeric inputs something reads, excluding axes, in sheet order."""
    return [c for c in read_structure(path)["inputs"] if c["dependents"] > 0 and not c["axis"]]


def _target(lever: str, message: str, path: str) -> dict[str, Any] | None:
    """The input cell the lever means on this workbook, by label. First by position when several match."""
    inputs = _inputs(path)
    if lever == "tariff":
        cell = key_cells(path)["tariff"]
        if cell == "Tariff":
            named = [c for c in inputs if "tariff" in (c["label"] or "").lower()]
            return named[0] if named else None
        return next((c for c in inputs if c["cell"] == cell), None)
    words = SYNONYMS[lever]
    matches = [c for c in inputs if any(w in (c["label"] or "").lower() for w in words)]
    if not matches:
        return None
    # "O&M rises" means the cost, not its escalation, unless the sentence says escalation.
    if "escalat" not in message.lower():
        plain = [c for c in matches if "escalat" not in (c["label"] or "").lower()]
        matches = plain or matches
    return matches[0]


def _row_note_scale(path: str, cell: str, before: float) -> float | None:
    """For a module price in INR/Wp: how many of the cell's units one INR/Wp is, from the row's note."""
    sheet, coord = cell.rsplit("!", 1)
    ws = load_workbook(path, data_only=False)[sheet]
    row = ws[coord].row
    for c in ws[row]:
        if isinstance(c.value, str):
            found = MODULE_PRICE.search(c.value)
            if found:
                return before / float(found.group(1))
    return None


def _change(message: str, before: float, path: str, cell: str) -> tuple[float, str] | None:
    """The new value and the words that asked for it. Order matters: the most specific form first."""
    sign = -1.0 if DOWN.search(message) and not UP.search(message) else 1.0
    if m := BASIS_POINTS.search(message):
        step = float(m.group(1)) / (100 if before > WHOLE_NUMBER_PERCENT else 10000)
        return before + sign * step, m.group(0)
    if m := RELATIVE_PERCENT.search(message):
        return before * (1 + sign * float(m.group(1)) / 100), m.group(0)
    if m := PER_WP.search(message):
        scale = _row_note_scale(path, cell, before)
        return (float(m.group(1)) * scale, m.group(0)) if scale else None
    if m := SET_PERCENT.search(message):
        pct = float(m.group(1))
        return (pct if before > WHOLE_NUMBER_PERCENT else pct / 100), m.group(0)
    if m := SET_NUMBER.search(message):
        return float(m.group(1)), m.group(0)
    return None


def parse_what_if(message: str, path: str) -> WhatIf | None:
    """The one input change a message asks for, or None when it asks for nothing we can do."""
    lever = _lever(message)
    if lever is None:
        return None
    target = _target(lever, message, path)
    if target is None or not isinstance(target["value"], (int, float)):
        return None
    before = float(target["value"])
    change = _change(message, before, path, target["cell"])
    if change is None:
        return None
    after, phrase = change
    return WhatIf(
        cell=target["cell"], label=target["label"] or target["cell"], before=before, after=after, phrase=phrase
    )


def asks_to_change_rivals(message: str) -> bool:
    """True when the message wants rival beliefs edited, which the Copilot must refuse."""
    return bool(RIVAL_WORDS.search(message) and EDIT_WORDS.search(message))
