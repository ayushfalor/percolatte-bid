"""Same checks on a workbook the app has never seen (different layout, no names, no cached values)."""
from __future__ import annotations

import pytest

from app.core.excel_engine import WorkbookEngine
from app.core.workbook_reader import find_by_label, read_structure


@pytest.fixture(scope="module")
def wind(wind_workbook):
    path, truth = wind_workbook
    return WorkbookEngine(str(path)), truth, str(path)


def test_recalculates_without_cached_values(wind):
    eng, truth, _ = wind
    assert eng.parity().status == "no_cached_values"
    got = eng.evaluate({}, [truth["equity_irr_cell"]])[truth["equity_irr_cell"]]
    assert got == pytest.approx(truth["equity_irr"], rel=1e-7)


def test_goal_seek_on_unseen_layout(wind):
    eng, truth, _ = wind
    res = eng.goal_seek(truth["tariff_cell"], truth["equity_irr_cell"], 0.12)
    assert res.converged and res.value == pytest.approx(truth["breakeven_12pct"], abs=1e-4)


def test_finds_labels_and_legacy_sheet(wind):
    _, truth, path = wind
    s = read_structure(path)
    roles = {x["name"]: x["role"] for x in s["sheets"]}
    assert roles[truth["legacy_sheet"]] == "legacy_candidate"
    assert find_by_label(s, [r"equity irr"], path) == truth["equity_irr_cell"]
    assert find_by_label(s, [r"^tariff"], path) == truth["tariff_cell"]
