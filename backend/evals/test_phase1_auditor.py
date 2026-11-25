"""Phase 1 gate: the Auditor understands the model and prices what is wrong."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.phase(1)
EXPECTED = json.loads((Path(__file__).parent / "expected" / "bid_model.json").read_text())
FACTS = json.loads((Path(__file__).parent / "expected" / "tender_facts.json").read_text())["facts"]


@pytest.fixture(scope="module")
def findings(samples):
    from app.core.audit import audit_workbook

    return audit_workbook(str(samples / "bid_model.xlsx"), tender_facts=FACTS)


@pytest.mark.parametrize("target", [pytest.param(t, id=f"{t['id']}:{t['where']}") for t in EXPECTED["auditor_targets"]])
def test_auditor_finds(findings, target):
    assert any(f.id == target["id"] and f.where == target["where"] for f in findings)


def test_every_finding_is_explained(findings):
    for f in findings:
        assert f.title and f.evidence and f.severity in {"high", "medium", "low", "info"}
        if f.severity == "high":
            assert f.impact_inr_per_kwh is not None and f.fix, f.id


def test_corrected_breakeven(samples):
    from app.core.audit import corrected_breakeven

    e = EXPECTED["corrected_breakeven"]
    assert corrected_breakeven(str(samples / "bid_model.xlsx")) == pytest.approx(e["value"], abs=e["tolerance"])


def test_fixes_never_touch_the_file(samples):
    from app.core.audit import corrected_breakeven

    path = samples / "bid_model.xlsx"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    corrected_breakeven(str(path))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_tornado_ranks_the_drivers(samples):
    from app.core.audit import tornado

    rows = tornado(str(samples / "bid_model.xlsx"))
    assert len(rows) >= 6
    swings = [r["swing"] for r in rows]
    assert swings == sorted(swings, reverse=True)
    assert {"Scenarios!D5", "Inputs!C8"} & {r["cell"] for r in rows[:2]}, "CUF should be a top-2 driver"
