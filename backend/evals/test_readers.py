"""What the Reader must get right on the three provided files."""
from __future__ import annotations

import pytest

from app.core.history_reader import read_history
from app.core.tender_reader import quote_on_page
from app.core.workbook_reader import read_structure


@pytest.fixture(scope="module")
def structure(samples):
    return read_structure(str(samples / "bid_model.xlsx"))


def test_workbook_basics(structure, expected):
    e = expected["bid_model"]
    assert structure["totals"]["sheets"] == e["sheets"]
    assert structure["totals"]["formulas"] == e["formula_cells"]
    assert structure["defined_names"] == e["defined_names"]
    hidden = [s["name"] for s in structure["sheets"] if s["state"] != "visible"]
    assert hidden == e["hidden_sheets"]


def test_sheet_roles(structure, expected):
    roles = {s["name"]: s["role"] for s in structure["sheets"]}
    for sheet, role in expected["bid_model"]["sheet_roles"].items():
        assert roles[sheet] == role, sheet


def test_unreferenced_inputs_are_surfaced(structure, expected):
    found = {u["cell"] for u in structure["unreferenced_numbers"]}
    assert set(expected["bid_model"]["unreferenced_inputs"]) <= found


def test_labels_come_from_the_sheet(structure):
    labels = {i["cell"]: i["label"] for i in structure["inputs"]}
    assert labels["Inputs!C12"] == "Tariff (bid)"
    assert labels["Inputs!C21"] == "Interest rate"


def test_tender_pages_and_numbering(tender_pages, expected):
    e = expected["tender_facts"]
    assert tender_pages["pages"] == e["pdf_pages"]
    assert tender_pages["needs_ocr"] == []
    page = tender_pages["page_texts"][20]
    assert page["pdf_page"] - page["printed_page"] == e["printed_page_offset"]


@pytest.mark.parametrize("fact", [pytest.param(f, id=f["field"]) for f in __import__("json").loads(
    (__import__("pathlib").Path(__file__).parent / "expected" / "tender_facts.json").read_text())["facts"]])
def test_golden_fact_quote_is_on_its_page(tender_pages, fact):
    """Golden set for the extractor: each fact's quote must exist on the cited page."""
    assert quote_on_page(fact["quote"], tender_pages["page_texts"][fact["pdf_page"] - 1]["text"])


def test_history_cleaning(samples, expected):
    h = read_history(str(samples / "auction_history.xlsx"))
    e = expected["history"]
    assert h["tenders"] == e["tenders"]
    assert h["bids"] == e["bids_after_dedupe"]
    assert h["duplicates_removed"] == e["duplicates_removed"]
    assert h["paise_tenders"] == e["paise_tenders"]
    assert h["raw_bidder_names"] == e["raw_bidder_names"]
    assert h["bidder_groups"] == e["bidder_groups"]
    assert h["categories"]["Solar (ISTS)"] == e["solar_ists_tenders"]


def test_all_six_agents_registered():
    from app.agents import REGISTRY

    assert list(REGISTRY) == ["reader", "auditor", "scout", "rival", "engine", "copilot"]
