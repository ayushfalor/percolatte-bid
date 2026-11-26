"""Phase 5: the Bid Brief, assembled from stored runs and nothing else.

The UI reads this; it never computes a number itself. Every figure here traces to an agent run
(auditor, rival, engine) or to a tender fact, so the three-second screen and the three-minute
verification are the same numbers.
"""

from __future__ import annotations

from typing import Any

from .contracts import Finding

CRORE = 1e7
MUST_DO_FACTS = {
    "emd": "emd_per_mw",
    "pbg": "pbg_per_mw",
    "success_charge": "success_charge_per_mw",
    "net_worth": "net_worth_per_mw",
}


def _certain(finding: Finding) -> bool:
    return bool(finding.fix) and not finding.assumptions and bool(finding.impact_inr_per_kwh)


def bridge_steps(findings: list[Finding], as_received: float, corrected: float) -> list[dict[str, Any]]:
    """From the model as received to the corrected breakeven, one step per certain fix.

    Steps carry {"label", "delta", "after", "assumed"}. Each fix's delta is its own measured
    impact. Fixes interact a little (insurance is charged on a year whose formula another fix
    restores), so the last certain step shows that interaction explicitly rather than hiding it
    in a rounded figure; the certain steps then add up exactly to corrected minus as_received. A
    step that rests on an assumption (the ALMM lever) comes after, marked assumed, and is not
    part of that total.
    """
    steps: list[dict[str, Any]] = []
    running = as_received
    for f in sorted((f for f in findings if _certain(f)), key=lambda f: -abs(f.impact_inr_per_kwh or 0)):
        running += f.impact_inr_per_kwh
        steps.append(
            {"label": f.title, "where": f.where, "delta": f.impact_inr_per_kwh, "after": running, "assumed": False}
        )
    residual = corrected - running
    if steps and abs(residual) > 1e-9:
        steps.append(
            {
                "label": "Interaction between the fixes",
                "where": None,
                "delta": residual,
                "after": corrected,
                "assumed": False,
            }
        )
    steps.extend(
        {
            "label": f"{f.title} (rests on {', '.join(f.assumptions)})",
            "where": f.where,
            "delta": f.impact_inr_per_kwh,
            "after": corrected + f.impact_inr_per_kwh,
            "assumed": True,
        }
        for f in findings
        if f.fix and f.assumptions and f.impact_inr_per_kwh
    )
    return steps


def _field(fact: Any, name: str, default: Any = None) -> Any:
    return fact.get(name, default) if isinstance(fact, dict) else getattr(fact, name, default)


def must_dos(facts: list[Any], our_mw: float = 200.0) -> dict[str, Any]:
    """What the bid team must have ready, in crore, each from a named tender fact."""
    by_field = {str(_field(f, "field")): f for f in facts}
    out: dict[str, Any] = {}
    for key, field in MUST_DO_FACTS.items():
        fact = by_field.get(field)
        if fact is None:
            continue
        per_mw = float(_field(fact, "value"))
        out[key] = {
            "cr": per_mw * our_mw / CRORE,
            "per_mw_inr": per_mw,
            "our_mw": our_mw,
            "from": field,
            "clause": str(_field(fact, "clause", "")),
            "pdf_page": _field(fact, "pdf_page"),
            "quote": str(_field(fact, "quote", "")),
        }
    return out
