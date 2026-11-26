"""Phase 5: the Copilot may only state numbers that came from a tool.

An answer is a string; the tools' outputs are numbers, possibly nested. Every number in the
answer has to round to a number some tool produced, in the units it was written in: ₹2.60 against
2.6039, 14% against 0.14, ₹16 Cr against 16.0 or 160,000,000. Things that look like numbers but
are not quantities, a clause, a section, a year, are left alone. What is left over is returned,
and an answer with anything left over is never shown.
"""

from __future__ import annotations

import re
from typing import Any

TOKEN = re.compile(
    r"(?<![A-Za-z\d.])(?P<prefix>[₹$]\s*|Rs\.?\s*|INR\s*)?(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<unit>%|crores?\b|cr\b|lakhs?\b|bp\b|bps\b|basis points?)?",
    re.I,
)
NOT_A_QUANTITY = re.compile(r"(clause|section|§|annexure|format|page|rfs|no\.?|#)\s*$", re.I)
YEAR = range(1900, 2101)
UNIT_SCALE = {
    "%": (0.01, 1.0),
    "cr": (1.0, 1e7),
    "crore": (1.0, 1e7),
    "crores": (1.0, 1e7),
    "lakh": (1.0, 1e5),
    "lakhs": (1.0, 1e5),
}


def _numbers(value: Any) -> list[float]:
    """Every number inside a tool output, however nested. Strings are not numbers."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    if isinstance(value, (list, tuple, set)):
        return [n for v in value for n in _numbers(v)]
    return []


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def _matches(candidate: float, decimals: int, pool: list[float]) -> bool:
    """A tool value supports the written number when it rounds to it at the precision written."""
    slack = 10.0 ** (-(decimals + 6))
    return any(abs(round(t, decimals) - round(candidate, decimals)) < slack for t in pool)


def _candidates(value: float, unit: str | None, decimals: int) -> list[tuple[float, int]]:
    """The values a written number could stand for, with the precision to compare at."""
    if not unit:
        return [(value, decimals)]
    key = unit.lower().rstrip(".")
    if key in ("bp", "bps") or key.startswith("basis"):
        return [(value, decimals), (value / 10000, decimals + 4), (value / 100, decimals + 2)]
    small, big = UNIT_SCALE.get(key, (1.0, 1.0))
    if key == "%":
        return [(value / 100, decimals + 2), (value, decimals)]
    return [(value * small, decimals), (value * big, max(decimals - 7, 0))]


def ungrounded_numbers(answer: str, tool_outputs: list[Any], tolerance: float = 0.005) -> list[str]:
    """Numbers in the answer that no tool output supports (after rounding). Empty list = safe to show."""
    pool = _numbers(tool_outputs)
    loose: list[str] = []
    for match in TOKEN.finditer(answer):
        raw, unit = match.group("num"), match.group("unit")
        before = answer[max(0, match.start() - 12) : match.start()]
        if NOT_A_QUANTITY.search(before):
            continue
        plain = raw.replace(",", "")
        value = float(plain)
        decimals = _decimals(plain)
        is_year = "," not in raw and decimals == 0 and int(value) in YEAR and not unit and not match.group("prefix")
        if is_year:
            continue
        if not any(_matches(c, d, pool) for c, d in _candidates(value, unit, decimals)):
            loose.append(raw)
    return loose
