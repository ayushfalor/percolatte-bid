"""Agent 1, Reader: extraction and normalization. Deterministic for Excel and history.

LLM tender extraction plugs in here later (structured output with page + quote,
verified with core.tender_reader.quote_on_page). In offline mode it loads the
cached extraction for the bundled tender.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from ..core.excel_engine import get_engine
from ..core.history_reader import read_history
from ..core.tender_extract import extract_facts, last_cost_usd, unusual_clauses
from ..core.tender_reader import read_pages
from ..core.workbook_reader import read_structure
from . import AgentContext, agent


@agent("reader", "Reader", "Reads workbooks, the tender PDF and auction history into clean, cited facts")
def run(ctx: AgentContext) -> dict[str, Any]:
    doc, path = ctx.document()
    ctx.progress(0.1, f"Reading {doc.filename}")
    if doc.kind == "workbook":
        result = read_structure(path)
        ctx.progress(0.5, "Recalculating every formula to compare with Excel")
        eng = get_engine(path)
        result["parity"] = eng.parity().as_dict()
        result["compile_ms"] = eng.compile_ms
        return result
    if doc.kind == "tender":
        result = read_pages(path)
        ctx.progress(0.5, f"{result['pages']} pages read, extracting the binding facts")
        facts = extract_facts(path, mode=ctx.params.get("mode", "auto"))
        unusual = unusual_clauses(path, mode=ctx.params.get("mode", "auto"))
        result["facts"] = [asdict(f) for f in facts]
        result["unusual_clauses"] = [asdict(f) for f in unusual]
        result["verified"] = sum(1 for f in facts if f.verified)
        result["sources"] = dict(Counter(f.source for f in facts))
        result["cost_usd"] = last_cost_usd()
        ctx.progress(0.9, f"{len(facts)} facts, {result['verified']} verified on their page")
        return result
    if doc.kind == "history":
        return read_history(path)
    raise ValueError(f"Reader does not know document kind '{doc.kind}'")
