"""The tender in plain words, for the bid team, from the facts the Reader verified.

Every number here is a fact's value formatted by code, with its clause beside it; the sentences
around the numbers are ours. The unusual clauses get a fixed explanation each: what the clause
says, and what it means for this bid. No model writes any of this, so it reads the same offline.
"""

from __future__ import annotations

import re
from typing import Any

from .brief import must_dos

OUR_MW = 200.0
CRORE = 1e7

# What each unusual clause means. Keys are the Reader's field names.
MEANING: dict[str, dict[str, str]] = {
    "almm_exempt": {
        "title": "Imported solar panels are allowed",
        "what": "Normally a government solar tender only accepts panels from an approved Indian list (ALMM). "
        "This tender waives that rule.",
        "for_us": "We can buy cheaper imported panels. In the bid model that is the difference between the "
        "INR 14.5/Wp Indian price and about INR 10/Wp imported, worth roughly 37 paise on the tariff. "
        "Rivals know this too, so expect lower bids than past auctions.",
    },
    "almm_exempt_confirmed": {
        "title": "The panel waiver is confirmed a second time",
        "what": "A later clause repeats that ALMM compliance is not required.",
        "for_us": "Two clauses say it, so the waiver is not a drafting slip. Price the bid on imported panels.",
    },
    "sez_status_loss_not_force_majeure": {
        "title": "If the SEZ loses its status, that is our problem",
        "what": "The buyers sit in a Special Economic Zone. If that status is withdrawn or its tax treatment "
        "changes, the tender says it is not an excuse to walk away or to reprice.",
        "for_us": "A policy change could hit our revenue or taxes and we would still have to deliver at the "
        "same tariff. Lenders will ask about this; keep a margin for it and do not bank on the zero GST lever.",
    },
    "gib_retrofit_rule": {
        "title": "Bird-safety retrofits on power lines may be ordered",
        "what": "In Great Indian Bustard habitat a court can order overhead lines to be moved underground "
        "or fitted with bird diverters, at the developer's cost.",
        "for_us": "If our site or line route is in that habitat, add the cost of underground cabling or "
        "diverters to capex before bidding. The bid model has no line for it today.",
    },
    "connectivity_grant_required": {
        "title": "A grid connection must already be granted",
        "what": "Bidders need an existing connectivity grant for the capacity they offer, not a pending application.",
        "for_us": "Fewer developers qualify, so the field is thinner than a normal solar auction. Check our "
        "grant covers the full 200 MW we plan to bid.",
    },
}

GENERIC = {
    "title": "A clause a normal solar tender does not have",
    "what": "The Reader flagged this clause as out of the ordinary.",
    "for_us": "Read the quoted text with the legal team before bidding.",
}


def explain(fact: dict[str, Any]) -> dict[str, str]:
    """What an unusual clause means, by its field name."""
    return MEANING.get(str(fact.get("field", "")), GENERIC)


def _value(facts: dict[str, Any], field: str) -> Any:
    fact = facts.get(field)
    return fact.get("value") if fact else None


def _is_clause(text: str) -> bool:
    """16.1, 41.2.c, 15.d: a clause number. Not 0.8, which is the share in '0.8 x ST'."""
    return re.fullmatch(r"[1-9]\d*(\.\d+)*(\.?[a-z])?", text) is not None


def _clause(facts: dict[str, Any], *fields: str) -> str:
    refs = [str(facts[f]["clause"]) for f in fields if f in facts and _is_clause(str(facts[f].get("clause", "")))]
    return f" (clause {', '.join(dict.fromkeys(refs))})" if refs else ""


def _offer(facts: dict[str, Any]) -> str | None:
    cap, low, high, step = (_value(facts, f) for f in ("se_cap_mw", "min_bid_mw", "max_bid_mw", "capacity_step_mw"))
    term, where = _value(facts, "ppa_term_years"), _value(facts, "drawl_point")
    if cap is None and low is None:
        return None
    parts = []
    if cap is not None:
        parts.append(f"SECI is buying up to {cap:.0f} MW of solar power")
    if low is not None and high is not None:
        parts.append(
            f"each bidder offers between {low:.0f} and {high:.0f} MW" + (f", in steps of {step:.0f} MW" if step else "")
        )
    text = "; ".join(parts) + _clause(facts, "se_cap_mw", "min_bid_mw") + "."
    if term is not None:
        text += f" The power purchase agreement runs {term:.0f} years{_clause(facts, 'ppa_term_years')}."
    if where:
        text += f" Power is delivered at {where}{_clause(facts, 'drawl_point')}."
    return text


def _money(facts_list: list[dict[str, Any]], facts: dict[str, Any]) -> str | None:
    dues = must_dos(facts_list, OUR_MW)
    if not dues:
        return None
    names = {"emd": "bid security (EMD)", "pbg": "performance guarantee (PBG)", "success_charge": "success charge"}
    bits = [f"{names.get(k, k)} INR {v['cr']:.1f} crore{_clause(facts, v['from'])}" for k, v in dues.items()]
    text = f"For a {OUR_MW:.0f} MW bid: " + ", ".join(bits) + "."
    worth = _value(facts, "net_worth_per_mw")
    if worth is not None:
        text += f" Net worth needed: INR {worth * OUR_MW / CRORE:.0f} crore{_clause(facts, 'net_worth_per_mw')}."
    text += " The EMD is lost if we withdraw or refuse an award we had to take."
    return text


def _auction(facts: dict[str, Any]) -> str | None:
    minutes, ext = _value(facts, "era_initial_minutes"), _value(facts, "era_extension_minutes")
    band, cut = _value(facts, "band_over_l1"), _value(facts, "min_decrement")
    refuse = _value(facts, "partial_refusal_threshold")
    if minutes is None and band is None:
        return None
    text = "First a sealed price, then a live auction where prices only go down."
    if minutes is not None:
        text += (
            f" It lasts {minutes:.0f} minutes"
            + (f", extended by {ext:.0f} minutes whenever a late move changes the standings" if ext else "")
            + _clause(facts, "era_initial_minutes")
            + "."
        )
    if cut is not None:
        text += f" Each cut is at least {cut * 100:.0f} paisa{_clause(facts, 'min_decrement')}."
    if band is not None:
        text += f" Only bids within {band:.0%} of the lowest price can win{_clause(facts, 'band_over_l1')}."
    if refuse is not None:
        ref = _clause(facts, "partial_refusal_threshold")
        text += (
            f" A partial award under {refuse:.0%} of what we offered may be refused; above that we must accept{ref}."
        )
    return text


def _deadlines(facts: dict[str, Any]) -> str | None:
    scsd, fc = _value(facts, "scsd_months_from_ppa"), _value(facts, "financial_closure_before_scsd_months")
    if scsd is None:
        return None
    when = _clause(facts, "scsd_months_from_ppa")
    text = f"The plant must be running {scsd:.0f} months after the agreement is signed{when}."
    if fc is not None:
        fc_ref = _clause(facts, "financial_closure_before_scsd_months")
        text += f" Financing must be closed {fc:.0f} months before that{fc_ref}."
    return text


def _performance(facts: dict[str, Any]) -> str | None:
    cuf, band, hours = _value(facts, "min_declared_cuf"), _value(facts, "cuf_band"), _value(facts, "cuf_hours_per_year")
    if cuf is None:
        return None
    text = f"We promise a capacity factor of at least {cuf:.0%}{_clause(facts, 'min_declared_cuf')}"
    if band:
        text += f", and actual generation must stay within {band} of the promise"
    text += "."
    if hours:
        text += f" The factor is measured on {hours:,.0f} hours a year{_clause(facts, 'cuf_hours_per_year')}."
    return text


def plain_summary(facts_list: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Short sections a bid manager reads in a minute. Sections whose facts are missing are left out."""
    facts = {str(f.get("field")): f for f in facts_list}
    sections = [
        ("What is on offer", _offer(facts)),
        ("Money we must put up", _money(facts_list, facts)),
        ("How the auction works", _auction(facts)),
        ("Deadlines", _deadlines(facts)),
        ("What we promise", _performance(facts)),
    ]
    return [{"heading": h, "text": t} for h, t in sections if t]
