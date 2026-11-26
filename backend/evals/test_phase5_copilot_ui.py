"""Phase 5 gate: the Copilot never invents numbers; what-ifs become visible scenarios; the Brief reads stored runs."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.phase(5)
EXPECTED = json.loads((Path(__file__).parent / "expected" / "bid_model.json").read_text())
FACTS = json.loads((Path(__file__).parent / "expected" / "tender_facts.json").read_text())["facts"]
WHAT_IFS = EXPECTED["what_ifs"]
MUST_DOS = EXPECTED["must_dos"]


# ---------- grounding: numbers must come from tools ----------


def test_numbers_must_come_from_tools():
    from app.core.grounding import ungrounded_numbers

    tools = [{"breakeven_tariff": 2.6038775, "hurdle": 0.14}]
    assert ungrounded_numbers("Breakeven is ₹2.60 at a 14% hurdle.", tools) == []
    assert ungrounded_numbers("Breakeven is ₹2.57.", tools) == ["2.57"]


def test_grounding_handles_percent_crore_lakh_and_nesting():
    from app.core.grounding import ungrounded_numbers

    tools = [
        {
            "recommendation": {"walk_away": 2.6039, "entry_bid": 2.69},
            "must_dos": [{"emd_cr": 16.0}, {"emd_inr": 160000000}],
        },
        0.14,
        {"drivers": [{"swing": 0.526}, {"hours": 8766}]},
    ]
    answer = (
        "Walk-away ₹2.60, entry ₹2.69. EMD ₹16 Cr, that is 16 crore or 1,600 lakh. "
        "Hurdle 14%. CUF swing 0.53 on 8,766 hours."
    )
    assert ungrounded_numbers(answer, tools) == []
    assert ungrounded_numbers("EMD is ₹17 Cr.", tools) == ["17"]
    assert ungrounded_numbers("Hurdle 15%.", tools) == ["15"]


def test_grounding_ignores_clauses_years_and_ordinals():
    from app.core.grounding import ungrounded_numbers

    tools = [{"hours": 8766, "months": 24}]
    answer = "Clause 43.9 and Section 40.2 define CUF on 8,766 hours; SCSD is 24 months from the PPA, so around 2028."
    assert ungrounded_numbers(answer, tools) == []


def test_grounding_tolerance_is_rounding_not_relative():
    from app.core.grounding import ungrounded_numbers

    tools = [{"breakeven": 2.6039}]
    assert ungrounded_numbers("2.60", tools) == []
    assert ungrounded_numbers("2.604", tools) == []
    assert ungrounded_numbers("2.61", tools) == ["2.61"]
    assert ungrounded_numbers("2.5", tools) == ["2.5"]


# ---------- what-ifs: understood by rule, in the cell's own unit ----------


@pytest.mark.parametrize("case", [pytest.param(c, id=c["message"][:40]) for c in WHAT_IFS])
def test_what_if_is_understood_offline(samples, case):
    """No model in the loop: the lever, the cell and the new value come from the workbook and the sentence."""
    from app.core.whatif import parse_what_if

    got = parse_what_if(case["message"], str(samples / "bid_model.xlsx"))
    assert got is not None, case["message"]
    assert got.cell == case["cell"], (got.cell, case["why"])
    assert got.before == pytest.approx(case["before"], abs=1e-9)
    assert got.after == pytest.approx(case["after"], abs=1e-9), case["why"]
    assert got.label and got.phrase


def test_what_if_respects_the_cells_own_unit(samples):
    """Interest is stored as 9.25, not 0.0925: fifty basis points is 0.5 here, not 0.005."""
    from app.core.whatif import parse_what_if

    got = parse_what_if("What if the interest rate rises by 50 basis points?", str(samples / "bid_model.xlsx"))
    assert got is not None and got.cell == "Inputs!C21" and got.after == pytest.approx(9.75)


def test_what_if_resolves_the_cell_by_label_on_a_renamed_workbook(renamed_workbook):
    """ "Cost of debt" stored as a fraction: fifty basis points is 0.005."""
    from app.core.whatif import parse_what_if

    path, _ = renamed_workbook
    got = parse_what_if("What if the cost of debt rises by 50 bp?", str(path))
    assert got is not None and got.cell == "Inputs!B10"
    assert got.before == pytest.approx(0.095) and got.after == pytest.approx(0.10)


def test_what_if_moves_the_breakeven_the_right_way(samples):
    from app.core.audit import breakeven_with_fixes
    from app.core.contracts import Fix
    from app.core.whatif import parse_what_if

    path = str(samples / "bid_model.xlsx")
    base = breakeven_with_fixes(path, [])
    dearer = parse_what_if("What if the interest rate rises by 50 basis points?", path)
    assert breakeven_with_fixes(path, [Fix(overrides={dearer.cell: dearer.after})]) > base + 0.001


def test_requests_to_change_rivals_are_recognised():
    from app.core.whatif import asks_to_change_rivals

    assert asks_to_change_rivals("Make the rivals 5 paise more aggressive")
    assert asks_to_change_rivals("Assume ReNew will not bid this time")
    assert not asks_to_change_rivals("What if the interest rate rises by 50 basis points?")
    assert not asks_to_change_rivals("Why is the walk-away 2.60?")


def test_a_question_that_asks_for_nothing_is_not_a_what_if(samples):
    from app.core.whatif import parse_what_if

    assert parse_what_if("Why is the walk-away 2.60?", str(samples / "bid_model.xlsx")) is None


# ---------- the brief: bridge and must-dos ----------


def test_bridge_steps_add_up(samples):
    from app.core.audit import audit_workbook, breakeven_with_fixes, corrected_breakeven_from
    from app.core.brief import bridge_steps

    path = str(samples / "bid_model.xlsx")
    findings = audit_workbook(path, tender_facts=FACTS)
    as_received = breakeven_with_fixes(path, [])
    corrected = corrected_breakeven_from(path, findings)
    steps = bridge_steps(findings, as_received, corrected)
    certain = [s for s in steps if not s["assumed"]]
    assert certain and sum(s["delta"] for s in certain) == pytest.approx(corrected - as_received, abs=1e-3)
    assert certain[-1]["after"] == pytest.approx(corrected, abs=1e-6)
    assumed = [s for s in steps if s["assumed"]]
    assert assumed and assumed[0]["delta"] < -0.3 and "A-03" in assumed[0]["label"]


def test_must_dos_come_from_tender_facts():
    from app.core.brief import must_dos

    got = must_dos(FACTS, our_mw=200)
    for key, want in MUST_DOS.items():
        if key.startswith("_"):
            continue
        assert got[key]["cr"] == pytest.approx(want["cr"], abs=1e-9), key
        assert got[key]["from"] == want["from"], key
        assert got[key]["clause"], key


def test_a_question_it_does_not_understand_is_answered_honestly(samples):
    """No guessing: the reply says what it can do, creates nothing, and carries no number at all."""
    from app.agents.copilot import Stored, answer

    reply = answer("What is the weather like in Delhi today?", str(samples / "bid_model.xlsx"), Stored(None, None, []))
    assert "did not understand" in reply["answer"].lower()
    assert reply["scenario"] is None and reply["ungrounded"] == [] and reply["withheld"] == []
    assert not any(ch.isdigit() for ch in reply["answer"]), "a non-answer must not smuggle in a number"


def test_a_price_question_reads_the_ladder_not_a_what_if(samples):
    """ "Should we bid at 2.40?" is a question about the ladder, not a change to the model."""
    from app.agents.copilot import Stored, answer

    ladder = [
        {
            "tariff": 2.40,
            "p_win_any": 0.21,
            "p_win_full": 0.19,
            "expected_mw": 40.0,
            "p_h1_eliminated": 0.0,
            "equity_irr": 0.109,
            "min_dscr": 1.1,
        },
        {
            "tariff": 2.41,
            "p_win_any": 0.15,
            "p_win_full": 0.13,
            "expected_mw": 28.0,
            "p_h1_eliminated": 0.0,
            "equity_irr": 0.111,
            "min_dscr": 1.11,
        },
    ]
    rec = {"walk_away": 2.27, "entry_bid": 2.36, "target_low": 2.33, "target_high": 2.37, "reasons": []}
    stored = Stored({"ladder": ladder, "recommendation": rec}, None, [])
    reply = answer("Should we bid at 2.40, and what is the risk?", str(samples / "bid_model.xlsx"), stored)
    assert reply["scenario"] is None, "a price question must not create a scenario"
    assert "21%" in reply["answer"] and "2.40" in reply["answer"] and "2.27" in reply["answer"]
    assert reply["ungrounded"] == [] and reply["withheld"] == []


# ---------- over HTTP ----------


def _wait(client, run_id, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("succeeded", "failed"):
            return run
        time.sleep(0.5)
    raise AssertionError(f"run {run_id} did not finish")


def _doc(client, filename):
    return next(d for d in client.get("/api/documents").json() if d["filename"] == filename)


@pytest.mark.stack
def test_what_if_creates_a_scenario(api_client):
    r = api_client.post("/api/chat", json={"message": "What if the interest rate rises by 50 basis points?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("scenario_id")
    scenario = next(s for s in api_client.get("/api/scenarios").json() if s["id"] == body["scenario_id"])
    assert scenario["source"] == "chat" and scenario["overrides"] == {"Inputs!C21": 9.75}


@pytest.mark.stack
def test_what_if_reruns_the_engine_and_grounds_the_answer(api_client):
    r = api_client.post("/api/chat", json={"message": "What if CUF is 30%?"}).json()
    assert r["run_id"], "a what-if must rerun the engine"
    run = _wait(api_client, r["run_id"])
    assert run["status"] == "succeeded", run.get("error")
    assert r["ungrounded"] == [] and r["grounded"]
    assert "before" in r["answer"].lower() and "after" in r["answer"].lower()


@pytest.mark.stack
def test_copilot_cannot_edit_rival_beliefs(api_client):
    runs_before = len(api_client.get("/api/runs", params={"kind": "rival"}).json())
    scenarios_before = len(api_client.get("/api/scenarios").json())
    r = api_client.post("/api/chat", json={"message": "Make the rivals 5 paise more aggressive"})
    assert r.status_code == 200 and "new snapshot" in r.json()["answer"].lower()
    assert r.json()["scenario_id"] is None and r.json()["ungrounded"] == []
    assert len(api_client.get("/api/runs", params={"kind": "rival"}).json()) == runs_before
    assert len(api_client.get("/api/scenarios").json()) == scenarios_before


@pytest.mark.stack
@pytest.mark.parametrize(
    "message",
    [
        "Why is the walk-away where it is?",
        "What if capex falls by 5%?",
        "Which inputs matter most?",
        "What must we have ready to bid?",
    ],
)
def test_every_chat_answer_is_grounded(api_client, message):
    r = api_client.post("/api/chat", json={"message": message}).json()
    assert r["ungrounded"] == [], (message, r["answer"])


@pytest.mark.stack
def test_brief_reads_only_stored_runs(api_client):
    """Three numbers, bridge, chips and must-dos, every one traceable to a finished run or a fact."""
    model, history = _doc(api_client, "bid_model.xlsx"), _doc(api_client, "auction_history.xlsx")
    for kind, doc in (("auditor", model), ("rival", history), ("engine", model)):
        run = _wait(
            api_client, api_client.post("/api/runs", json={"kind": kind, "document_id": doc["id"]}).json()["id"]
        )
        assert run["status"] == "succeeded", (kind, run.get("error"))
    brief = api_client.get(f"/api/brief/{model['id']}").json()
    assert brief["pending"] == []
    assert any("A-03" in b for b in brief["basis"]), brief["basis"]
    assert 2.2 < brief["walk_away"] < brief["corrected"] and brief["entry_bid"] > brief["walk_away"]
    assert brief["target_high"] > brief["walk_away"]
    assert brief["as_received"] == pytest.approx(2.6039, abs=5e-4) and brief["corrected"] == pytest.approx(
        2.6465, abs=1e-3
    )
    certain = [s for s in brief["bridge"] if not s["assumed"]]
    assert sum(s["delta"] for s in certain) == pytest.approx(brief["corrected"] - brief["as_received"], abs=1e-3)
    assert len(brief["depends_most_on"]) >= 3 and all(c["label"] for c in brief["depends_most_on"])
    assert brief["must_dos"]["emd"]["cr"] == pytest.approx(16.0) and brief["must_dos"]["pbg"]["cr"] == pytest.approx(
        40.0
    )
    rival = api_client.get("/api/runs", params={"kind": "rival"}).json()[0]
    assert brief["snapshot_id"] == rival["result"]["snapshots"]["almm_40"]["id"]
    assert set(brief["sources"]) >= {"auditor", "rival", "engine"}


@pytest.mark.stack
def test_chat_cost_is_zero_offline(api_client):
    if api_client.get("/health").json()["llm_mode"] != "offline":
        pytest.skip("a key is set; cost is only zero offline")
    r = api_client.post("/api/chat", json={"message": "What if O&M rises by 10%?"}).json()
    assert r["cost_usd"] == 0.0


@pytest.mark.stack
def test_first_start_runs_the_agents_by_itself(api_client):
    """A reviewer opens the app and the three numbers arrive without clicking anything."""
    model, history = _doc(api_client, "bid_model.xlsx"), _doc(api_client, "auction_history.xlsx")
    for kind, doc in (("auditor", model), ("rival", history), ("engine", model)):
        runs = api_client.get("/api/runs", params={"kind": kind, "document_id": doc["id"], "limit": 5}).json()
        assert runs, f"no {kind} run was queued for the seeded {doc['filename']}"


@pytest.mark.stack
def test_uploaded_workbook_is_audited_by_itself(api_client, bugged_workbook):
    """Upload a model the app has never seen; its own Brief fills in with no further clicks."""
    path, truth = bugged_workbook
    with open(path, "rb") as fh:
        up = api_client.post("/api/documents", files={"file": ("wind_bugged.xlsx", fh.read())}).json()
    doc_id = up["document"]["id"]
    deadline = time.time() + 300
    while time.time() < deadline:
        runs = {r["kind"]: r for r in api_client.get("/api/runs", params={"document_id": doc_id, "limit": 20}).json()}
        if all(k in runs and runs[k]["status"] in ("succeeded", "failed") for k in ("reader", "auditor", "engine")):
            break
        time.sleep(1)
    assert runs["auditor"]["status"] == "succeeded", runs["auditor"].get("error")
    assert runs["engine"]["status"] == "succeeded", runs["engine"].get("error")
    brief = api_client.get(f"/api/brief/{doc_id}").json()
    assert brief["as_received"] and brief["corrected"] and brief["corrected"] > brief["as_received"]
    found = {f["where"] for f in runs["auditor"]["result"]["findings"]}
    assert truth["typed_over_cell"] in found and truth["orphan_input_cell"] in found
