"""Phase 5: the Bid Brief, assembled from stored runs and nothing else.

The UI reads this; it never computes a number itself. Every figure here traces to an agent run
(auditor, rival, engine) or to a tender fact, so the three-second screen and the three-minute
verification are the same numbers.
"""

from __future__ import annotations

from typing import Any

from .contracts import Finding


def bridge_steps(findings: list[Finding], as_received: float, corrected: float) -> list[dict[str, Any]]:
    """From the model as received to the corrected breakeven, one step per certain fix.

    Steps carry {"label", "delta", "after", "assumed"}. Certain steps add up to corrected minus
    as_received. A step that rests on an assumption (the ALMM lever) is listed after the corrected
    figure with assumed=True and is not part of that total.
    """
    raise NotImplementedError("Phase 5: brief not built yet")


def must_dos(facts: list[Any], our_mw: float = 200.0) -> dict[str, Any]:
    """What the bid team must have ready, in crore, each from a named tender fact."""
    raise NotImplementedError("Phase 5: brief not built yet")
