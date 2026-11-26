"""Phase 5: what a what-if means, worked out from the workbook, with no model in the loop.

The Copilot has to run with no API key, so the common levers are understood by rule: which input
the sentence is about (by label, the same way the Auditor finds cells), how much it moves, and in
the cell's own unit. A cell that stores 9.25 for 9.25% moves by 0.5 for 50 basis points; one that
stores 0.095 moves by 0.005. Numbers always come from the workbook; the model, when there is one,
only words the answer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhatIf:
    cell: str  # the input the sentence is about, e.g. "Inputs!C21"
    label: str  # what the workbook calls it
    before: float
    after: float
    phrase: str  # the part of the message that named the change, for the scenario's name


def parse_what_if(message: str, path: str) -> WhatIf | None:
    """The one input change a message asks for, or None when it asks for nothing we can do."""
    raise NotImplementedError("Phase 5: what-if parsing not built yet")


def asks_to_change_rivals(message: str) -> bool:
    """True when the message wants rival beliefs edited, which the Copilot must refuse."""
    raise NotImplementedError("Phase 5: what-if parsing not built yet")
