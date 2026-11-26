"""Phase 2: tender facts with proof.

Two ways to get a fact, both ending in the same check:

  rule   a pattern over the page text, anchored on the RfS's own wording. Deterministic, needs
         no key, and is what a reviewer without a key runs. Every value is parsed out of the
         matched text, the page is the page it was found on, and the clause is the numbered
         heading that precedes it.
  llm    one structured pass over the pages when an API key is present. Cached by file hash in
         `data/cache/`, so the second run is free and offline. Rules fill any field the model
         misses.

Whichever way a fact arrives, its quote is checked on its page by code before it is trusted.
A fact that fails that check is kept and marked `verified=False`, never silently dropped.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..keys import api_key, llm_mode
from .contracts import TenderFact
from .tender_reader import quote_on_page, read_pages

log = logging.getLogger(__name__)

CLAUSE = re.compile(r"(?<![\d.])(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?![\d.])\s+[A-Z(]")
LIVE_PAGE_CHARS = 2500  # per page sent to the model; the binding core is dense but short
LIVE_MAX_PAGES = 70  # bid information sheet, sections 1 to 6 and Annexure-B all sit before this
USD_PER_MILLION = {"input": 3.0, "output": 15.0}  # approximate list price, for the cost line only
_LAST_COST_USD = 0.0


@dataclass(frozen=True)
class Rule:
    """One fact, found by the RfS's own wording. `q` is the quote group, `v` the value group."""

    field: str
    unit: str
    pattern: str
    kind: str  # inr | int | float | pct | flag | text | band

    def value(self, match: re.Match) -> Any:
        groups = match.groupdict()
        raw = groups.get("v", "")
        if self.kind == "flag":
            return True
        if self.kind == "text":
            return raw.strip()
        if self.kind == "band":
            return f"+{groups['a']}% / -{groups['b']}%"
        number = float(raw.replace(",", ""))
        if self.kind == "pct":
            return number / 100
        return int(number) if self.kind in ("inr", "int") else number


INR = r"INR\s+(?P<v>[\d,]+)/MW"
LAKH = r"\(Indian Rupees[^)]*\)"

RULES: list[Rule] = [
    Rule("emd_per_mw", "INR/MW", rf"(?:Earnest Money|EMD).{{0,400}}?(?P<q>{INR}\s*{LAKH})", "inr"),
    Rule("pbg_per_mw", "INR/MW", rf"(?:Performance Bank Guarantee|PBG).{{0,400}}?(?P<q>{INR}/Project)", "inr"),
    Rule(
        "success_charge_per_mw",
        "INR/MW plus taxes",
        rf"Success Charge.{{0,400}}?(?P<q>{INR}\s*{LAKH}\s*\+\s*applicable taxes)",
        "inr",
    ),
    Rule("min_bid_mw", "MW", r"(?P<q>minimum quantum of Contracted Capacity of (?P<v>\d+) MW)", "int"),
    Rule("max_bid_mw", "MW", r"(?P<q>maximum quantum of (?P<v>\d+) MW)", "int"),
    Rule("capacity_step_mw", "MW", r"(?P<q>quoted in multiples of (?P<v>\d+) MW only)", "int"),
    Rule("min_declared_cuf", "fraction", r"(?P<q>shall in no case be less than (?P<v>\d+)%)", "pct"),
    Rule(
        "cuf_band",
        "of declared CUF",
        r"(?P<q>within \+\s*(?P<a>\d+)% and -\s*(?P<b>\d+)% of the declared value)",
        "band",
    ),
    Rule("cuf_hours_per_year", "hours", r"(?P<q>MW\*(?P<v>8766))", "int"),
    Rule(
        "scsd_months_from_ppa",
        "months",
        r"(?P<q>shall be the date as on (?P<v>\d+) months from the Effective Date of the PPA)",
        "int",
    ),
    Rule(
        "financial_closure_before_scsd_months",
        "months",
        r"(?P<q>Financial Closure by the date as on (?P<v>\d+) months prior to the SCSD)",
        "int",
    ),
    Rule("ppa_term_years", "years from SCSD", r"(?P<q>valid for a period of (?P<v>\d+) years from the SCSD)", "int"),
    Rule("band_over_l1", "fraction of L1", r"(?P<q>\+\s*(?P<v>\d+)% of the L1 tariff)", "pct"),
    Rule("se_cap_mw", "MW", r"(?P<q>subject to maximum eligible capacity being (?P<v>\d+) MW)", "int"),
    Rule(
        "min_decrement",
        "INR/kWh",
        r"(?P<q>The minimum decrement value for tariff shall be INR (?P<v>[\d.]+) per kWh)",
        "float",
    ),
    Rule(
        "era_initial_minutes", "minutes", r"(?P<q>initial auction period will be of (?P<v>\d+) \(\w+\) minutes)", "int"
    ),
    Rule("era_extension_minutes", "minutes", r"(?P<q>auto extension by (?P<v>\d+) \(\w+\) minutes)", "int"),
    Rule(
        "partial_refusal_threshold",
        "of quoted capacity",
        r"(?P<q>lower than (?P<v>\d+)% of the total quoted capacity)",
        "pct",
    ),
    Rule(
        "almm_exempt",
        "flag",
        r"(?P<q>exemption from Approved List of Models and Manufacturers \(ALMM\) requirements)",
        "flag",
    ),
    Rule("almm_exempt_confirmed", "flag", r"(?P<q>exempted from compliance with the ALMM requirements)", "flag"),
    Rule("sez_status_loss_not_force_majeure", "flag", r"(?P<q>these risks do not constitute a)", "flag"),
    Rule("trading_margin", "INR/kWh", r"(?P<q>shall be @ INR (?P<v>[\d.]+)/kWh)", "float"),
    Rule("net_worth_per_mw", "INR/MW", rf"Net[\s-]?Worth.{{0,400}}?(?P<q>{INR}\s*{LAKH})", "inr"),
    Rule("drawl_point", "text", r"(?P<q>(?P<v>Paradeep ISTS Substation))", "text"),
    Rule("gib_retrofit_rule", "flag", r"(?P<q>Great Indian Bustard)", "flag"),
]

# Clauses a vanilla ISTS solar tender does not have. The bid team needs to see these first.
UNUSUAL: list[Rule] = [
    RULES[18],  # ALMM exemption
    RULES[20],  # loss of SEZ status is the developer's risk
    RULES[24],  # Great Indian Bustard retrofits
    Rule(
        "connectivity_grant_required",
        "flag",
        r"(?P<q>[^.]{0,160}\bconnectivity\b[^.]{0,200}\bgrant(?:ed)?\b[^.]{0,120})",
        "flag",
    ),
]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _clause_before(flat: str, position: int) -> str:
    found = [m.group(1) for m in CLAUSE.finditer(flat, 0, position)]
    return found[-1] if found else ""


def _apply_rules(pages: list[dict[str, Any]], rules: list[Rule]) -> list[TenderFact]:
    """The first page each rule matches on, read in page order. Needs no key."""
    found: list[TenderFact] = []
    for rule in rules:
        regex = re.compile(rule.pattern, re.I | re.S)
        for page in pages:
            flat = _flat(page["text"])
            match = regex.search(flat)
            if match is None:
                continue
            quote = _flat(match.group("q")).strip()
            found.append(
                TenderFact(
                    field=rule.field,
                    value=rule.value(match),
                    unit=rule.unit,
                    clause=_clause_before(flat, match.start("q")),
                    pdf_page=page["pdf_page"],
                    printed_page=page.get("printed_page"),
                    quote=quote,
                    verified=quote_on_page(quote, page["text"]),
                    source="rule",
                )
            )
            break
    return found


# ---------- the live pass, when a key is present ----------


def _cache_file(path: str) -> Path:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return Path(get_settings().cache_dir) / f"{digest}.json"


def _read_cache(path: str) -> list[TenderFact] | None:
    file = _cache_file(path)
    if not file.is_file():
        return None
    data = json.loads(file.read_text())
    return [TenderFact(**{**f, "source": "cache"}) for f in data["facts"]]


def _write_cache(path: str, facts: list[TenderFact], meta: dict[str, Any]) -> None:
    file = _cache_file(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"meta": meta, "facts": [asdict(f) for f in facts]}, indent=1))


def _prompt(pages: list[dict[str, Any]]) -> str:
    wanted = "\n".join(f"- {r.field} ({r.unit})" for r in RULES)
    body = "\n\n".join(
        f"[pdf_page {p['pdf_page']}]\n{_flat(p['text'])[:LIVE_PAGE_CHARS]}"
        for p in pages[:LIVE_MAX_PAGES]
        if p["text"].strip()
    )
    return (
        "You are reading an Indian solar tender (RfS). For each field below, find the binding value.\n"
        "Return ONLY a JSON array of objects with keys: field, value, unit, clause, pdf_page, quote.\n"
        "`quote` must be copied exactly from the page text, 4 to 20 words, and `pdf_page` must be the\n"
        "page it was copied from. Use true for flags. Percentages as fractions. Omit a field you cannot find.\n\n"
        f"Fields:\n{wanted}\n\nPages:\n{body}"
    )


def _llm_facts(path: str, pages: list[dict[str, Any]]) -> list[TenderFact]:
    """One structured call. Quotes are verified by code on the cited page; nothing is taken on trust."""
    global _LAST_COST_USD
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=api_key())
    response = client.messages.create(
        model=settings.llm_model_smart,
        max_tokens=4000,
        messages=[{"role": "user", "content": _prompt(pages)}],
    )
    usage = response.usage
    _LAST_COST_USD = (
        usage.input_tokens * USD_PER_MILLION["input"] + usage.output_tokens * USD_PER_MILLION["output"]
    ) / 1e6
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    start, end = text.find("["), text.rfind("]")
    rows = json.loads(text[start : end + 1]) if start >= 0 and end > start else []
    by_page = {p["pdf_page"]: p for p in pages}
    facts: list[TenderFact] = []
    for row in rows:
        page = by_page.get(int(row.get("pdf_page", 0)))
        quote = str(row.get("quote", ""))
        facts.append(
            TenderFact(
                field=str(row.get("field", "")),
                value=row.get("value"),
                unit=str(row.get("unit", "")),
                clause=str(row.get("clause", "")),
                pdf_page=int(row.get("pdf_page", 0)),
                printed_page=page.get("printed_page") if page else None,
                quote=quote,
                verified=bool(page) and quote_on_page(quote, page["text"]),
                source="llm",
            )
        )
    return facts


def last_cost_usd() -> float:
    """What the most recent live extraction cost; zero for rules and the cache."""
    return _LAST_COST_USD


def _merge(primary: list[TenderFact], fallback: list[TenderFact]) -> list[TenderFact]:
    """Keep every verified primary fact; fill the rest from the fallback."""
    have = {f.field for f in primary if f.verified}
    return [f for f in primary if f.verified] + [f for f in fallback if f.field not in have]


def extract_facts(path: str, mode: str = "auto") -> list[TenderFact]:
    """The binding facts of the RfS, each with page and a quote checked on that page.

    mode="auto": live if ANTHROPIC_API_KEY is set, else the cached result for this file's hash,
    else the rules. mode="rule" forces the rules; mode="live" requires a key.
    """
    pages = read_pages(path)["page_texts"]
    by_rule = _apply_rules(pages, RULES)
    if mode == "rule":
        return by_rule
    live = llm_mode() == "live"
    if mode == "live" and not live:
        raise RuntimeError("mode='live' needs ANTHROPIC_API_KEY")
    if not live:
        cached = _read_cache(path)
        return _merge(cached, by_rule) if cached else by_rule
    try:
        facts = _merge(_llm_facts(path, pages), by_rule)
    except Exception as exc:  # a failed call must not take the tender down with it
        log.warning("Live extraction failed (%s); using rules", exc)
        return by_rule
    _write_cache(path, facts, {"model": get_settings().llm_model_smart, "cost_usd": _LAST_COST_USD})
    return facts


def unusual_clauses(path: str, mode: str = "auto") -> list[TenderFact]:
    """Clauses that differ from a vanilla ISTS solar tender: ALMM, SEZ risk, GIB, connectivity."""
    return _apply_rules(read_pages(path)["page_texts"], UNUSUAL)
