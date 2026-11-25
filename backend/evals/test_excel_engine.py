"""Correctness and speed of the formula engine on the provided bid model."""

from __future__ import annotations

import time

import pytest


def test_engine_matches_every_excel_value(bid_engine, expected):
    report = bid_engine.parity()
    assert report.status == "match", report.mismatches[:5]
    assert report.formula_cells == expected["bid_model"]["formula_cells"]


@pytest.mark.parametrize("name", ["equity_irr", "project_irr_as_built", "min_dscr"])
def test_kpis(bid_engine, expected, name):
    kpi = expected["bid_model"]["kpis"][name]
    got = bid_engine.evaluate({}, [kpi["cell"]])[kpi["cell"]]
    assert got == pytest.approx(kpi["value"], abs=1e-9)


@pytest.mark.parametrize("case", ["goal_seek", "goal_seek_dscr"])
def test_goal_seek(bid_engine, expected, case):
    g = expected["bid_model"][case]
    res = bid_engine.goal_seek(g["variable"], g["target"], g["target_value"])
    assert res.converged, res.message
    assert res.value == pytest.approx(g["expected"], abs=g["tolerance"])


def test_named_range_and_cell_overrides_agree(bid_engine):
    by_name = bid_engine.evaluate({"Tariff": 2.5}, ["Returns!C8"])["Returns!C8"]
    by_cell = bid_engine.evaluate({"Inputs!C12": 2.5}, ["Returns!C8"])["Returns!C8"]
    assert by_name == pytest.approx(by_cell, abs=1e-12)


def test_overrides_never_touch_the_file(bid_engine):
    before = bid_engine.evaluate({}, ["Returns!C8"])["Returns!C8"]
    bid_engine.evaluate({"Tariff": 2.0}, ["Returns!C8"])
    assert bid_engine.evaluate({}, ["Returns!C8"])["Returns!C8"] == before


def test_scenario_switch_low_case_is_worse(bid_engine):
    base = bid_engine.evaluate({}, ["Returns!C8"])["Returns!C8"]
    low = bid_engine.evaluate({"Scenario": 2}, ["Returns!C8"])["Returns!C8"]
    assert low < base


def test_bad_reference_gives_a_fixable_error(bid_engine):
    from app.core.excel_engine import EngineError

    with pytest.raises(EngineError, match="No sheet named"):
        bid_engine.evaluate({}, ["Nope!A1"])


def test_speed_budget(bid_engine):
    t0 = time.perf_counter()
    bid_engine.evaluate({"Tariff": 2.55}, ["Returns!C8"])
    assert time.perf_counter() - t0 < 2.0
    t0 = time.perf_counter()
    bid_engine.goal_seek("Tariff", "Returns!C8", 0.14)
    assert time.perf_counter() - t0 < 15.0
