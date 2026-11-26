"""Agent 6, Copilot: chat about the current scenario. Tools only, no LLM arithmetic.

What-ifs become Scenario rows (visible in the UI), then the Engine reruns. It can read the rival
snapshot but never change it. Every number in an answer comes from a tool output, and the answer
is checked by core.grounding before it is shown; one it cannot trace is withheld, not shown.

The wording is templated, so it works with no API key. A model, when a key exists, could reword
the same facts; it would never be allowed to add a number.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..core.audit import breakeven_with_fixes
from ..core.brief import must_dos
from ..core.contracts import Fix
from ..core.grounding import ungrounded_numbers
from ..core.simulate import TARGET_SHARE, TYPICAL_CUT
from ..core.whatif import WhatIf, asks_to_change_rivals, parse_what_if
from . import AgentContext, agent

POLICY = {"target_share": TARGET_SHARE, "typical_cut_paise": round(TYPICAL_CUT * 100), "max_h1_risk": 0.05}
WITHHELD = (
    "I had a number I could not trace back to a tool, so I have not shown it. "
    "Ask again and I will show only what the tools say."
)
RIVALS_FROZEN = (
    "I cannot change what we believe about rivals from here. Rival beliefs are frozen once computed, "
    "so a fair comparison stays fair. To see a different field, run the Rival model again with another "
    "regime or seed; that gives you a new snapshot to switch to."
)


def _fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


class Stored:
    """The latest finished results the Copilot may quote. Nothing here is computed by the Copilot."""

    def __init__(self, engine: dict[str, Any] | None, auditor: dict[str, Any] | None, facts: list[Any]):
        self.engine, self.auditor, self.facts = engine or {}, auditor or {}, facts


def _what_if_answer(wi: WhatIf, path: str) -> tuple[str, list[Any]]:
    base = breakeven_with_fixes(path, [])
    after = breakeven_with_fixes(path, [Fix(overrides={wi.cell: wi.after})])
    tools = [
        {"cell": wi.cell, "before": wi.before, "after": wi.after},
        {"breakeven_before": base, "breakeven_after": after},
    ]
    move = (after - base) * 100
    text = (
        f"Scenario saved: {wi.label} from {_fmt(wi.before, 4)} to {_fmt(wi.after, 4)} ({wi.cell}). "
        f"Before: the 14% breakeven is ₹{base:.4f}. After: ₹{after:.4f}, "
        f"{'up' if move >= 0 else 'down'} {abs(move):.2f} paise. "
        "The Engine is rerunning the ladder with this change; the War Room shows it as a ghost curve when done."
    )
    tools.append({"move_paise": move, "hurdle_percent": 14})
    return text, tools


def _recommendation_answer(stored: Stored) -> tuple[str, list[Any]]:
    rec = stored.engine.get("recommendation")
    if not rec:
        return "There is no price ladder yet. Run the Rival model and then the Engine, and ask me again.", []
    text = " ".join(rec.get("reasons", [])) or (
        f"Walk-away ₹{rec['walk_away']:.2f}, target ₹{rec['target_low']:.2f} to ₹{rec['target_high']:.2f}, "
        f"entry ₹{rec['entry_bid']:.2f}."
    )
    return text, [rec, POLICY]


def _drivers_answer(stored: Stored) -> tuple[str, list[Any]]:
    drivers = stored.auditor.get("drivers") or []
    if not drivers:
        return "The Auditor has not ranked the inputs yet. Run it and ask me again.", []
    top = drivers[:3]
    text = (
        "It depends most on " + "; ".join(f"{d['label']} (swing ₹{d['swing']:.2f} on the breakeven)" for d in top) + "."
    )
    return text, [top]


def _must_do_answer(stored: Stored) -> tuple[str, list[Any]]:
    items = must_dos(stored.facts)
    if not items:
        return "I do not have the tender facts yet. Run the Reader on the RfS and ask me again.", []
    names = {"emd": "EMD", "pbg": "PBG", "success_charge": "Success charge", "net_worth": "Net worth"}
    parts = [
        f"{names.get(k, k)} ₹{v['cr']:.1f} Cr "
        f"(₹{v['per_mw_inr']:,.0f} per MW on {v['our_mw']:.0f} MW, clause {v['clause']})"
        for k, v in items.items()
    ]
    return "To bid you need: " + "; ".join(parts) + ".", [items]


def _findings_answer(stored: Stored) -> tuple[str, list[Any]]:
    findings = stored.auditor.get("findings") or []
    priced = [f for f in findings if f.get("impact_inr_per_kwh")]
    if not priced:
        return "The Auditor has not run on this model yet.", []
    top = sorted(priced, key=lambda f: -abs(f["impact_inr_per_kwh"]))[:3]
    text = (
        "The biggest problems: "
        + "; ".join(f"{f['title']} at {f['where']}, worth {f['impact_inr_per_kwh'] * 100:+.1f} paise" for f in top)
        + "."
    )
    return text, [top, {"paise": [f["impact_inr_per_kwh"] * 100 for f in top]}]


def answer(message: str, path: str, stored: Stored) -> dict[str, Any]:
    """The reply, the scenario it created (if any), and the tool outputs every number came from."""
    text, tools, scenario = "", [], None
    lower = message.lower()
    if asks_to_change_rivals(message):
        text = RIVALS_FROZEN
    elif (wi := parse_what_if(message, path)) is not None:
        text, tools = _what_if_answer(wi, path)
        scenario = {"name": f"{wi.label}: {wi.phrase}", "overrides": {wi.cell: wi.after}, "what_if": asdict(wi)}
    elif any(w in lower for w in ("walk-away", "walk away", "entry", "target", "recommend", "ladder", "bid at")):
        text, tools = _recommendation_answer(stored)
    elif any(w in lower for w in ("matter", "driver", "sensitiv", "depends", "tornado")):
        text, tools = _drivers_answer(stored)
    elif any(w in lower for w in ("ready", "must", "emd", "pbg", "guarantee", "net worth", "eligib")):
        text, tools = _must_do_answer(stored)
    elif any(w in lower for w in ("wrong", "problem", "finding", "bug", "fix", "audit")):
        text, tools = _findings_answer(stored)
    else:
        text, tools = _recommendation_answer(stored)

    loose = ungrounded_numbers(text, tools)
    if loose:
        text, tools = WITHHELD, []
    grounded = [f"{k}={v}" for t in tools if isinstance(t, dict) for k, v in t.items() if isinstance(v, (int, float))]
    return {
        "answer": text,
        "scenario": scenario,
        "grounded": grounded,
        "ungrounded": [],
        "withheld": loose,
        "cost_usd": 0.0,
    }


@agent("copilot", "Copilot", "Answers what-if questions by creating scenarios and rerunning the engine")
def run(ctx: AgentContext) -> dict[str, Any]:
    """The same answer through the queue, for the audit log. The API path is synchronous."""
    _, path = ctx.document()
    stored = Stored(ctx.latest_result("engine"), ctx.latest_result("auditor"), ctx.params.get("facts", []))
    return answer(str(ctx.params.get("message", "")), path, stored)
