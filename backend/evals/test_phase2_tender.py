"""Phase 2 gate: tender facts with proof, offline-safe."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.phase(2)
GOLDEN = json.loads((Path(__file__).parent / "expected" / "tender_facts.json").read_text())["facts"]


@pytest.fixture(scope="module")
def facts(samples):
    from app.core.tender_extract import extract_facts

    return {f.field: f for f in extract_facts(str(samples / "tender.pdf"))}


@pytest.mark.parametrize("gold", [pytest.param(g, id=g["field"]) for g in GOLDEN])
def test_golden_fact(facts, gold):
    got = facts[gold["field"]]
    assert got.value == gold["value"] and got.pdf_page == gold["pdf_page"]


def test_quotes_are_verified_by_code(facts):
    verified = sum(1 for f in facts.values() if f.verified)
    assert verified / len(facts) >= 0.95


def test_unusual_clauses_found(samples):
    from app.core.tender_extract import unusual_clauses

    fields = {f.field for f in unusual_clauses(str(samples / "tender.pdf"))}
    assert {"almm_exempt", "sez_status_loss_not_force_majeure", "gib_retrofit_rule"} <= fields
    assert any("connectivity" in f for f in fields)


def test_offline_mode_needs_no_key(samples, monkeypatch):
    from app.config import get_settings
    from app.core.tender_extract import extract_facts

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    try:
        facts = extract_facts(str(samples / "tender.pdf"), mode="auto")
        assert facts and all(f.source in ("cache", "rule") for f in facts)
    finally:
        get_settings.cache_clear()
