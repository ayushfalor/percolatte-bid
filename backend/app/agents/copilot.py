"""Agent 6, Copilot: chat about the current scenario. Tools only, no LLM arithmetic.

What-ifs become Scenario rows (visible in the UI), then the Engine reruns. It can read the rival
snapshot but never change it. Every number in an answer comes from a tool output, and the answer
is checked by core.grounding before it is shown; one it cannot trace is withheld, not shown.

The wording is templated, so it works with no API key. A model, when a key exists, could reword
the same facts; it would never be allowed to add a number.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from typing import Any

from ..config import get_settings
from ..core.audit import breakeven_with_fixes
from ..core.brief import must_dos
from ..core.contracts import Fix
from ..core.grounding import ungrounded_numbers
from ..core.simulate import TARGET_SHARE, TYPICAL_CUT
from ..core.whatif import WhatIf, asks_to_change_rivals, parse_what_if
from ..keys import api_key, llm_mode
from . import AgentContext, agent

log = logging.getLogger(__name__)

POLICY = {
    "target_share": TARGET_SHARE,
    "typical_cut_paise": round(TYPICAL_CUT * 100),
    "max_h1_risk": 0.05,
    "our_mw": 200,
}
WITHHELD = (
    "I had a number I could not trace back to a tool, so I have not shown it. "
    "Ask again and I will show only what the tools say."
)
CANNOT_ANSWER = (
    "I did not understand that, and I would rather say so than guess. I can do four things: "
    "run a what-if on an input of the model (for example, what if the interest rate rises by fifty basis points, "
    "or what if CUF is thirty percent); explain the walk-away, target and entry bid; say which inputs matter most; "
    "and list what must be ready to bid. Ask one of those and every number I give you comes from a tool."
)
USD_PER_MILLION = {"input": 3.0, "output": 15.0}  # approximate list price, for the cost line only
MAX_ANSWER_TOKENS = 1500  # the model may think before it writes, and that counts against this budget
SYSTEM = (
    "You are the Copilot of a bid workbench for a solar developer bidding in SECI's 700 MW C&I-1 tender. "
    "Answer the question in plain English, in at most five sentences. You have one source of truth: the DATA "
    "block, which holds numbers computed by the workbook's own formulas and the auction rules. Use only numbers "
    "that appear in DATA, written the way they appear (tariffs in INR per kWh to two decimals, percentages as "
    "percents, money in crore). If the question needs a number that is not in DATA, say you do not have it. "
    "Never invent a figure, a clause, or a rival. Do not give advice beyond what DATA supports. If the question is "
    "not about this bid at all, say so in one sentence and offer what you can help with, and include no number."
)
PRICE_QUESTION = re.compile(r"\b(?:bid|bidding|price|tariff|quote)\b[^\d]{0,40}?(\d\.\d{1,2})\b", re.I)
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


def _price_point_answer(stored: Stored, price: float) -> tuple[str, list[Any]]:
    """What the ladder says at one price: odds, MW, returns, and where it sits against the floor."""
    ladder = stored.engine.get("ladder") or []
    rec = stored.engine.get("recommendation") or {}
    if not ladder or not rec:
        return "There is no price ladder yet. Run the Rival model and then the Engine, and ask me again.", []
    p = min(ladder, key=lambda q: abs(q["tariff"] - price))
    gap = (p["tariff"] - rec["walk_away"]) * 100
    side = "above" if gap >= 0 else "below"
    text = (
        f"At ₹{p['tariff']:.2f}: {p['p_win_any']:.0%} chance of winning anything, {p['p_win_full']:.0%} of winning all "
        f"{POLICY['our_mw']} MW, {p['expected_mw']:.0f} MW expected, "
        f"{p['p_h1_eliminated']:.0%} chance of going out as H1. "
        f"Equity IRR {p['equity_irr']:.1%}"
        + (f", minimum DSCR {p['min_dscr']:.2f}" if p.get("min_dscr") is not None else "")
        + f". That is {abs(gap):.0f} paise {side} the walk-away of ₹{rec['walk_away']:.2f}"
        + (
            ": below the floor is a loss, whatever the odds."
            if gap < 0
            else f"; the target range is ₹{rec['target_low']:.2f} to ₹{rec['target_high']:.2f}."
        )
    )
    return text, [p, rec, {"gap_paise": abs(gap), "our_mw": POLICY["our_mw"]}]


def _data_for_model(stored: Stored) -> dict[str, Any]:
    """The only facts the model may speak from: stored runs and tender facts, nothing it could invent."""
    findings = sorted(stored.auditor.get("findings") or [], key=lambda f: -abs(f.get("impact_inr_per_kwh") or 0))
    return {
        "breakeven_as_received": stored.auditor.get("breakeven_as_received"),
        "corrected_breakeven": stored.auditor.get("corrected_breakeven"),
        "recommendation": stored.engine.get("recommendation"),
        "floor_basis": stored.engine.get("basis"),
        "drivers": (stored.auditor.get("drivers") or [])[:5],
        "findings": [
            {
                "title": f["title"],
                "where": f["where"],
                "severity": f["severity"],
                "impact_inr_per_kwh": f["impact_inr_per_kwh"],
            }
            for f in findings[:8]
        ],
        "must_dos": must_dos(stored.facts),
        "policy": POLICY,
        "hurdle_equity_irr": stored.engine.get("hurdle", 0.14),
        "price_grid_inr_per_kwh": [2.0, 2.8],
        "tender_facts": {
            str(f.get("field") if isinstance(f, dict) else getattr(f, "field", "")): (
                f.get("value") if isinstance(f, dict) else getattr(f, "value", None)
            )
            for f in stored.facts
        },
    }


def _llm_answer(message: str, stored: Stored) -> tuple[str, list[Any], float]:
    """A model words the answer from DATA alone. Grounding still checks every number it writes."""
    import anthropic

    settings = get_settings()
    data = _data_for_model(stored)
    try:
        client = anthropic.Anthropic(api_key=api_key())
        response = client.messages.create(
            model=settings.llm_model_smart,
            max_tokens=MAX_ANSWER_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"DATA:\n{json.dumps(data, default=str)}\n\nQUESTION: {message}"}],
        )
    except Exception as exc:  # the model being down must not take the Copilot down
        log.warning("Copilot model call failed: %s", exc)
        return CANNOT_ANSWER, [], 0.0
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()
    if getattr(response, "stop_reason", "") == "max_tokens":
        log.warning("Copilot answer hit the token budget; the reply may be cut short")
    usage = response.usage
    cost = (usage.input_tokens * USD_PER_MILLION["input"] + usage.output_tokens * USD_PER_MILLION["output"]) / 1e6
    return (text or CANNOT_ANSWER), [data], cost


def answer(message: str, path: str, stored: Stored) -> dict[str, Any]:
    """The reply, the scenario it created (if any), and the tool outputs every number came from.

    Rules first: what-ifs, rival requests and the common questions are deterministic and need no
    key. With a key, anything the rules cannot answer goes to the model with the stored results as
    its only data. Either way, a number that no tool produced never reaches the screen.
    """
    text, tools, scenario, cost = "", [], None, 0.0
    lower = message.lower()
    if asks_to_change_rivals(message):
        text = RIVALS_FROZEN
    elif "what if" not in lower and (price := PRICE_QUESTION.search(message)) is not None:
        text, tools = _price_point_answer(stored, float(price.group(1)))
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
    elif llm_mode() == "live":
        text, tools, cost = _llm_answer(message, stored)
    else:
        text, tools = CANNOT_ANSWER, []

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
        "cost_usd": cost,
    }


@agent("copilot", "Copilot", "Answers what-if questions by creating scenarios and rerunning the engine")
def run(ctx: AgentContext) -> dict[str, Any]:
    """The same answer through the queue, for the audit log. The API path is synchronous."""
    _, path = ctx.document()
    stored = Stored(ctx.latest_result("engine"), ctx.latest_result("auditor"), ctx.params.get("facts", []))
    return answer(str(ctx.params.get("message", "")), path, stored)
