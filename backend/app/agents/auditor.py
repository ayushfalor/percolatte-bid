"""Agent 2, Auditor: model bugs, tender-vs-model mismatches, each priced in INR/kWh.

Every number here comes from the formula engine, never from an LLM. The agent gathers what the
checks found, prices the fixes and hands the worker a result to store.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..core.audit import audit_workbook, breakeven_with_fixes, corrected_breakeven_from, tornado
from . import AgentContext, agent


def _tender_facts(ctx: AgentContext) -> list[dict[str, Any]]:
    """Facts from the tender agent's latest run.

    Empty until Phase 2 lands, which is fine: the model-against-itself checks do not need them.
    """
    tender = ctx.latest_result("tender") or {}
    return list(tender.get("facts", []))


@agent("auditor", "Auditor", "Finds model bugs and tender mismatches, prices each fix in INR/kWh")
def run(ctx: AgentContext) -> dict[str, Any]:
    _, path = ctx.document()
    facts = _tender_facts(ctx)
    hurdle = float(ctx.params.get("hurdle", 0.14))

    ctx.progress(0.1, "Reading the model's shape")
    findings = audit_workbook(path, tender_facts=facts, target_irr=hurdle)

    ctx.progress(0.6, f"Pricing {len(findings)} findings")
    as_received = breakeven_with_fixes(path, [], target_irr=hurdle)
    corrected = corrected_breakeven_from(path, findings, target_irr=hurdle)

    ctx.progress(0.8, "Ranking the drivers")
    drivers = tornado(path, top_n=int(ctx.params.get("top_n", 8)), target_irr=hurdle)

    ctx.progress(1.0, f"{len(findings)} findings, breakeven {as_received:.4f} to {corrected:.4f}")
    return {
        "hurdle": hurdle,
        "tender_facts_used": len(facts),
        "breakeven_as_received": as_received,
        "corrected_breakeven": corrected,
        "findings": [asdict(f) for f in findings],
        "drivers": drivers,
    }
