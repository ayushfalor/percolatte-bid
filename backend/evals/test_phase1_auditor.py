"""Phase 1 gate: the Auditor understands the model and prices what is wrong."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.phase(1)
EXPECTED = json.loads((Path(__file__).parent / "expected" / "bid_model.json").read_text())
FACTS = json.loads((Path(__file__).parent / "expected" / "tender_facts.json").read_text())["facts"]
RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}
IMPACTS = {k: v for k, v in EXPECTED["auditor_impacts"].items() if not k.startswith("_")}
IMPACT_TOL = EXPECTED["auditor_impacts"]["_tolerance"]


@pytest.fixture(scope="module")
def findings(samples):
    from app.core.audit import audit_workbook

    return audit_workbook(str(samples / "bid_model.xlsx"), tender_facts=FACTS)


def _one(findings, key: str):
    """The single finding for an 'id:where' key from the golden file."""
    want_id, where = key.split(":", 1)
    matches = [f for f in findings if f.id == want_id and f.where == where]
    assert len(matches) == 1, f"expected exactly one {key}, got {len(matches)}"
    return matches[0]


# ---------- what it finds ----------

@pytest.mark.parametrize("target", [pytest.param(t, id=f"{t['id']}:{t['where']}") for t in EXPECTED["auditor_targets"]])
def test_auditor_finds(findings, target):
    assert any(f.id == target["id"] and f.where == target["where"] for f in findings)


@pytest.mark.parametrize("target", [pytest.param(t, id=f"{t['id']}:{t['where']}") for t in EXPECTED["auditor_targets"]])
def test_finding_severity_matches_expected(findings, target):
    got = _one(findings, f"{target['id']}:{target['where']}")
    assert got.severity == target["severity"], target["why"]


def test_every_finding_is_explained(findings):
    for f in findings:
        assert f.title and f.evidence and f.severity in {"high", "medium", "low", "info"}
        if f.severity == "high":
            assert f.impact_inr_per_kwh is not None and f.fix, f.id


def test_cosmetic_input_is_not_confused_with_an_orphan(findings):
    """Inputs!C28 is money nobody charged. Inputs!C13 cannot change anything whatever its value."""
    assert _one(findings, "orphan_input:Inputs!C28").id == "orphan_input"
    assert _one(findings, "cosmetic_input:Inputs!C13").id == "cosmetic_input"
    assert not [f for f in findings if f.id == "orphan_input" and f.where == "Inputs!C13"]
    assert not [f for f in findings if f.id == "cosmetic_input" and f.where == "Inputs!C28"]


@pytest.mark.parametrize("case", [pytest.param(c, id=c["where"]) for c in EXPECTED["not_findings"]])
def test_deliberate_and_benign_cells_are_not_bugs(findings, case):
    """Unused on purpose, or consistent with its own label. Reporting these as problems is noise."""
    worst = [f for f in findings if f.where == case["where"] and RANK[f.severity] > RANK[case["max_severity"]]]
    assert not worst, f"{case['where']}: {case['why']}"


def test_stale_note_is_measured_against_the_live_number(findings):
    note = _one(findings, "stale_note:Returns!C16")
    assert "2.57" in note.evidence
    assert "2.60" in note.evidence or "2.6039" in note.evidence, "say what the number really is"


def test_truncated_range_names_both_ranges_and_both_irrs(findings):
    """It does not move the price. It misreports project IRR, so the evidence has to carry the proof."""
    f = _one(findings, "truncated_range:Returns!C9")
    assert "AA" in f.evidence and "AB" in f.evidence, f.evidence
    assert "11.3" in f.evidence and "11.4" in f.evidence, f.evidence


# ---------- what each finding is worth ----------

@pytest.mark.parametrize("key", sorted(IMPACTS))
def test_known_impacts(findings, key):
    got = _one(findings, key).impact_inr_per_kwh
    assert got is not None, f"{key} must be priced"
    assert got == pytest.approx(IMPACTS[key]["impact"], abs=IMPACT_TOL), IMPACTS[key]["why"]


@pytest.mark.parametrize("key", sorted(EXPECTED["zero_impact_findings"]))
def test_findings_that_cannot_move_the_price_say_so(findings, key):
    got = _one(findings, key).impact_inr_per_kwh
    assert got == 0 or got is None, EXPECTED["zero_impact_findings"][key]["why"]


def test_impact_matches_applying_the_fix(samples, findings):
    """The number has to be what the fix actually does, not a remembered constant.

    Applying one finding's own fix on its own must move the breakeven by exactly its stated impact.
    """
    from app.core.audit import breakeven_with_fixes

    path = str(samples / "bid_model.xlsx")
    base = breakeven_with_fixes(path, [])
    priced = [f for f in findings if f.fix and f.impact_inr_per_kwh]
    assert len(priced) >= 4, "at least the two model bugs and the two tender mismatches are priced"
    for f in priced:
        got = breakeven_with_fixes(path, [f.fix])
        assert got - base == pytest.approx(f.impact_inr_per_kwh, abs=IMPACT_TOL), f"{f.id}:{f.where}"


def test_tender_mismatch_impact_cites_its_assumption_and_clauses(findings):
    almm = _one(findings, "tender_mismatch:Capex!D5")
    assert almm.assumptions == ("A-03",), "an impact that rests on an assumed price must cite it"
    assert set(almm.clauses) >= {"3.3", "35.2"}, almm.clauses
    hours = _one(findings, "tender_mismatch:Inputs!C11")
    assert hours.clauses == ("43.9",)
    assert not hours.assumptions, "8766 comes straight from the RfS, nothing is assumed"


# ---------- the corrected breakeven ----------

def test_corrected_breakeven(samples):
    from app.core.audit import corrected_breakeven

    e = EXPECTED["corrected_breakeven"]
    assert corrected_breakeven(str(samples / "bid_model.xlsx")) == pytest.approx(e["value"], abs=e["tolerance"])


def test_corrected_breakeven_excludes_assumption_backed_fixes(samples, findings):
    """D-011: certain fixes only. The ALMM re-price is worth tens of paise, so this is observable."""
    from app.core.audit import breakeven_with_fixes, corrected_breakeven

    path = str(samples / "bid_model.xlsx")
    almm = _one(findings, "tender_mismatch:Capex!D5")
    assert abs(almm.impact_inr_per_kwh) > 0.30, "the lever we are deliberately leaving out is a big one"
    with_almm = breakeven_with_fixes(path, [f.fix for f in findings if f.fix and f.impact_inr_per_kwh])
    assert abs(corrected_breakeven(path) - with_almm) > 0.30


def test_fixes_never_touch_the_file(samples):
    """Every entry point writes to a temp copy, never to what the user uploaded."""
    from app.core.audit import audit_workbook, corrected_breakeven, tornado

    path = samples / "bid_model.xlsx"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    audit_workbook(str(path), tender_facts=FACTS)
    corrected_breakeven(str(path))
    tornado(str(path))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


# ---------- labels and the tornado ----------

def test_labels_come_from_column_headers_when_the_row_text_is_not_the_name(samples):
    """Scenarios!D5 sits in the 'Base' row under the 'CUF (AC)' header. The header names it."""
    from app.core.audit import tornado

    rows = {r["cell"]: r["label"] for r in tornado(str(samples / "bid_model.xlsx"), top_n=12)}
    for cell, label in EXPECTED["labels"].items():
        if cell.startswith("_"):
            continue
        assert cell in rows, f"{cell} should be a driver"
        assert label.lower() in rows[cell].lower(), f"{cell} labelled {rows[cell]!r}, expected {label!r}"


def test_tornado_ranks_the_drivers(samples):
    from app.core.audit import tornado

    rows = tornado(str(samples / "bid_model.xlsx"))
    assert len(rows) >= 6
    swings = [r["swing"] for r in rows]
    assert swings == sorted(swings, reverse=True)
    assert {"Scenarios!D5", "Inputs!C8"} & {r["cell"] for r in rows[:2]}, "CUF should be a top-2 driver"


def test_tornado_rows_are_labelled_and_live(samples):
    from app.core.audit import tornado

    rows = tornado(str(samples / "bid_model.xlsx"))
    dead = {c["where"] for c in EXPECTED["auditor_targets"] if c["id"] in {"orphan_input", "cosmetic_input"}}
    for r in rows:
        assert r["label"] and r["label"].strip(), r["cell"]
        assert r["cell"] not in dead, f"{r['cell']} changes nothing, it cannot be a driver"
        assert r["swing"] == pytest.approx(abs(r["high"] - r["low"]), abs=1e-9)


def test_tornado_is_fast_enough(samples):
    from app.core.audit import tornado

    t0 = time.perf_counter()
    tornado(str(samples / "bid_model.xlsx"))
    elapsed = time.perf_counter() - t0
    assert elapsed < EXPECTED["tornado_seconds"], f"tornado took {elapsed:.1f}s"


# ---------- a workbook the app has never seen ----------

def test_auditor_on_an_unseen_workbook(bugged_workbook):
    """Different layout, different labels, no cached values, ground truth computed in Python.

    An implementation that remembers the solar sample's cells finds nothing here.
    """
    from app.core.audit import audit_workbook

    path, truth = bugged_workbook
    found = audit_workbook(str(path))
    typed = [f for f in found if f.id == "hardcode_in_formula_row" and f.where == truth["typed_over_cell"]]
    orphan = [f for f in found if f.id == "orphan_input" and f.where == truth["orphan_input_cell"]]
    legacy = [f for f in found if f.id == "legacy_sheet" and f.where == truth["legacy_sheet"]]
    assert typed, f"did not find the number typed over the O&M formula at {truth['typed_over_cell']}"
    assert orphan, f"did not find the unreferenced insurance input at {truth['orphan_input_cell']}"
    assert legacy, f"did not find the hidden legacy sheet {truth['legacy_sheet']}"


def test_unseen_workbook_impacts_match_python_ground_truth(bugged_workbook):
    from app.core.audit import audit_workbook, breakeven_with_fixes

    path, truth = bugged_workbook
    target = truth["target_irr"]
    found = {(f.id, f.where): f for f in audit_workbook(str(path))}
    base = breakeven_with_fixes(str(path), [], target_irr=target)
    assert base == pytest.approx(truth["breakeven"], abs=1e-4)

    for key, want in (
        (("hardcode_in_formula_row", truth["typed_over_cell"]), truth["impact_typed_over"]),
        (("orphan_input", truth["orphan_input_cell"]), truth["impact_insurance"]),
    ):
        f = found[key]
        assert f.impact_inr_per_kwh == pytest.approx(want, abs=1e-3), key
        got = breakeven_with_fixes(str(path), [f.fix], target_irr=target)
        assert got - base == pytest.approx(want, abs=1e-3), key


def test_unseen_workbook_insurance_fix_is_wired_generically(bugged_workbook):
    """The insurance fix has to reach every year of the cost row, found through labels and the
    reference graph, not from a cell address we remembered from the solar sample."""
    from app.core.audit import audit_workbook

    path, truth = bugged_workbook
    orphan = next(f for f in audit_workbook(str(path)) if f.id == "orphan_input")
    assert orphan.fix, "an orphan input that can be priced must carry its fix"
    assert set(orphan.fix.touches) == set(truth["om_row_cells"]), orphan.fix.touches


def test_unseen_workbook_file_is_never_written(bugged_workbook):
    from app.core.audit import audit_workbook, tornado

    path, _ = bugged_workbook
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    audit_workbook(str(path))
    tornado(str(path))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


# ---------- over HTTP ----------

@pytest.mark.stack
def test_findings_endpoint(api_client):
    """What an external eval suite would hit: findings for the seeded bid model, as JSON."""
    docs = api_client.get("/api/documents").json()
    wb = next(d for d in docs if d["filename"] == "bid_model.xlsx")
    r = api_client.get(f"/api/workbooks/{wb['id']}/findings")
    assert r.status_code == 200, r.text
    body = r.json()
    found = {(f["id"], f["where"]) for f in body["findings"]}
    assert {(t["id"], t["where"]) for t in EXPECTED["auditor_targets"]} <= found
    e = EXPECTED["corrected_breakeven"]
    assert body["corrected_breakeven"] == pytest.approx(e["value"], abs=e["tolerance"])
