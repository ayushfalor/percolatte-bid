"""Phase 2: tender facts with proof. Contract only; see evals/test_phase2_tender.py."""
from __future__ import annotations

from .contracts import TenderFact


def extract_facts(path: str, mode: str = "auto") -> list[TenderFact]:
    """LLM pass 1 (typed facts) on the binding core, quotes checked on the cited page.

    mode="auto": live if ANTHROPIC_API_KEY is set, else the cached result for a known file hash.
    """
    raise NotImplementedError("Phase 2: tender extraction not built yet")


def unusual_clauses(path: str, mode: str = "auto") -> list[TenderFact]:
    """LLM pass 2: clauses that differ from a vanilla ISTS solar tender (ALMM, SEZ risk, GIB...)."""
    raise NotImplementedError("Phase 2: tender extraction not built yet")
