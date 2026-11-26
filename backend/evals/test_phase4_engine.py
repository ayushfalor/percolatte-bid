"""Phase 4 gate: the price ladder is consistent with the RfS and with common sense."""

from __future__ import annotations

import time
from itertools import pairwise

import numpy as np
import pytest

pytestmark = pytest.mark.phase(4)


@pytest.fixture(scope="module")
def snapshot(samples):
    from app.core.history_reader import read_history
    from app.core.rival_model import build_snapshot

    return build_snapshot(read_history(str(samples / "auction_history.xlsx")), "almm_40", seed=42)


@pytest.fixture(scope="module")
def economics(bid_engine):
    grid = [round(2.0 + i * 0.05, 2) for i in range(17)]
    rows = []
    for t in grid:
        v = bid_engine.evaluate({"Tariff": t}, ["Returns!C8", "Returns!C10"])
        rows.append({"tariff": t, "equity_irr": v["Returns!C8"], "min_dscr": v["Returns!C10"]})
    return rows


@pytest.fixture(scope="module")
def ladder(snapshot, economics):
    from app.core.simulate import price_ladder

    return price_ladder(snapshot, economics, seed=42)


def test_win_odds_fall_as_price_rises(ladder):
    odds = [p.p_win_any for p in ladder]
    assert all(a >= b - 1e-12 for a, b in pairwise(odds))


def test_extremes_make_sense(ladder):
    assert ladder[-1].p_win_any < 0.05 and ladder[0].p_win_any > 0.5
    assert all(0 <= p.expected_mw <= 200 for p in ladder)


def test_ladder_is_internally_consistent(ladder):
    for p in ladder:
        assert 0 <= p.p_win_full <= p.p_win_any <= 1, p.tariff
        assert p.expected_mw <= 200 * p.p_win_any + 1e-9, p.tariff
        assert 0 <= p.p_h1_eliminated <= 1


def test_same_seed_same_ladder(snapshot, economics, ladder):
    from app.core.simulate import price_ladder

    again = price_ladder(snapshot, economics, seed=42)
    assert [p.p_win_any for p in again] == [p.p_win_any for p in ladder]


def test_cost_what_if_changes_profit_not_win_odds(snapshot, economics, ladder):
    from app.core.simulate import price_ladder

    pricier = [{**e, "equity_irr": e["equity_irr"] - 0.01} for e in economics]
    other = price_ladder(snapshot, pricier, seed=42)
    assert [p.p_win_any for p in other] == [p.p_win_any for p in ladder]
    assert [p.equity_irr for p in other] != [p.equity_irr for p in ladder]


def test_expected_value_is_win_weighted_npv(snapshot, economics):
    """When the workbook gives equity value above the hurdle, EV is that value times the MW we expect."""
    from app.core.simulate import price_ladder

    with_npv = [{**e, "npv_cr": 100 * (e["tariff"] - 2.3)} for e in economics]
    for p in price_ladder(snapshot, with_npv, seed=42):
        assert p.npv_cr == pytest.approx(100 * (p.tariff - 2.3), abs=1e-9)
        assert p.expected_value_cr == pytest.approx(p.expected_mw / 200 * p.npv_cr, abs=1e-9)


def test_vectorised_rules_match_the_scalar_rules():
    """Rule 6: the ladder's settlement is the same code path as the RfS worked examples, proven."""
    from app.core import auction_rules as r

    rng = np.random.default_rng(3)
    for _ in range(200):
        n = int(rng.integers(3, 9))
        part = rng.random(n) < 0.8
        mw = rng.choice([100.0, 200.0, 300.0, 400.0], n)
        floors = np.round(rng.uniform(2.2, 2.7, n), 2)
        opens = np.round(floors + rng.uniform(0.01, 0.15, n), 2)
        price = float(np.round(rng.uniform(2.2, 2.8), 2))
        got = r.settle_field(part[None, :], floors[None, :], mw[None, :], opens[None, :], price)

        names = [f"R{j}" for j in range(n)]
        sealed = [r.Bid(names[j], mw[j], opens[j]) for j in range(n) if part[j]] + [r.Bid("Us", 200, price)]
        short = r.shortlist_for_era(sealed)
        we_out = "Us" in short.eliminated
        assert bool(got["h1_eliminated"][0]) == we_out, (price, sealed)
        finals = [r.Bid(names[j], mw[j], floors[j], 0.0) for j in range(n) if part[j] and names[j] in short.shortlisted]
        finals.append(r.Bid("Us", 200, price, 1.0))
        award = r.allocate(finals, short.eligible_mw).for_bidder("Us")
        expect = 0.0 if we_out else award.awarded_mw
        assert got["win_mw"][0] == pytest.approx(expect), (price, [(b.bidder, b.capacity_mw, b.tariff) for b in finals])


def test_walk_away_is_the_stricter_of_irr_and_dscr(ladder):
    from app.core.simulate import recommend

    assert recommend(ladder, hurdle_tariff=2.28, dscr_tariff=2.10).walk_away == pytest.approx(2.28)
    assert recommend(ladder, hurdle_tariff=2.28, dscr_tariff=2.35).walk_away == pytest.approx(2.35)


def test_recommendation_hangs_together(ladder):
    from app.core.simulate import recommend

    rec = recommend(ladder, hurdle_tariff=2.28)
    assert rec.walk_away <= rec.target_low <= rec.target_high
    assert rec.entry_bid >= rec.walk_away
    assert len(rec.reasons) >= 3 and all(rec.reasons)


def test_entry_bid_rarely_gets_knocked_out(ladder):
    from app.core.simulate import recommend

    rec = recommend(ladder, hurdle_tariff=2.28)
    point = min(ladder, key=lambda p: abs(p.tariff - rec.entry_bid))
    assert point.p_h1_eliminated <= 0.05


def test_replay_follows_the_rfs(snapshot):
    from app.core.simulate import replay

    events = replay(snapshot, draw_index=0, our_open=2.45, our_floor=2.28)
    for e in events:
        if e.get("type") == "bid":
            assert e["new"] < e["old"] and round((e["old"] - e["new"]) * 100, 6) >= 1  # cuts only, 1 paisa minimum
    assert events[-1]["minute"] >= 30


def test_replay_never_goes_below_our_floor_and_extends_on_late_moves(snapshot):
    from app.core.simulate import replay

    events = replay(snapshot, draw_index=1, our_open=2.60, our_floor=2.30)
    ours = [e for e in events if e.get("type") == "bid" and e["bidder"] == "Us"]
    assert all(e["new"] >= 2.30 - 1e-9 for e in ours)
    extensions = [e for e in events if e.get("type") == "extension"]
    assert all(e["until"] - e["minute"] <= 8 + 1e-9 for e in extensions)
    assert events[-1]["type"] == "end" and events[-1]["awards"]


def test_runtime_budget(snapshot, economics):
    from app.core.simulate import price_ladder

    t0 = time.perf_counter()
    price_ladder(snapshot, economics, seed=7)
    assert time.perf_counter() - t0 < 60


def test_engine_agent_builds_the_ladder_from_a_stored_rival_run(samples):
    """The agent as the worker drives it: a rival run already stored, then the engine."""
    from types import SimpleNamespace

    from app.agents.modeling import run as engine
    from app.agents.rival import run as rival
    from app.config import get_settings

    history = str(samples / "auction_history.xlsx")
    rival_ctx = SimpleNamespace(
        params={},
        settings=get_settings(),
        document=lambda: (SimpleNamespace(kind="history", filename="auction_history.xlsx"), history),
        progress=lambda *_: None,
    )
    stored = rival(rival_ctx)
    model = str(samples / "bid_model.xlsx")
    engine_ctx = SimpleNamespace(
        params={"step": 0.1},
        settings=get_settings(),
        document=lambda: (SimpleNamespace(kind="workbook", filename="bid_model.xlsx"), model),
        progress=lambda *_: None,
        latest_result=lambda kind, document_id=None: stored if kind == "rival" else None,
    )
    out = engine(engine_ctx)
    assert len(out["ladder"]) == 81 and out["snapshot_id"] == stored["snapshots"]["almm_40"]["id"]
    rec = out["recommendation"]
    assert rec["walk_away"] == pytest.approx(max(out["breakeven_tariff"], out["dscr_tariff"]), abs=1e-9)
    assert out["breakeven_tariff"] == pytest.approx(2.6039, abs=5e-4) and out["dscr_tariff"] == pytest.approx(
        2.3757, abs=5e-4
    )
    assert rec["entry_bid"] >= rec["walk_away"] and rec["reasons"]


@pytest.mark.stack
def test_ladder_over_http(api_client):
    """What an external eval suite would do: run rivals, run the engine, read the three numbers."""
    docs = api_client.get("/api/documents").json()
    history = next(d for d in docs if d["filename"] == "auction_history.xlsx")
    model = next(d for d in docs if d["filename"] == "bid_model.xlsx")

    def wait(run_id):
        for _ in range(240):
            run = api_client.get(f"/api/runs/{run_id}").json()
            if run["status"] in ("succeeded", "failed"):
                return run
            time.sleep(0.5)
        raise AssertionError(f"run {run_id} did not finish")

    rival = wait(api_client.post("/api/runs", json={"kind": "rival", "document_id": history["id"]}).json()["id"])
    assert rival["status"] == "succeeded", rival.get("error")
    engine = wait(api_client.post("/api/runs", json={"kind": "engine", "document_id": model["id"]}).json()["id"])
    assert engine["status"] == "succeeded", engine.get("error")
    body = engine["result"]
    assert len(body["ladder"]) == 81
    assert body["as_received_breakeven"] == pytest.approx(2.6039, abs=5e-4)
    # With the Auditor's certain fixes and the ALMM lever applied, the floor is where the field is.
    assert any("A-03" in b for b in body["basis"]), body["basis"]
    assert 2.2 < body["recommendation"]["walk_away"] < 2.35, body["recommendation"]
    assert body["recommendation"]["entry_bid"] > body["recommendation"]["walk_away"]


def test_entry_and_target_never_sit_below_the_walk_away(ladder):
    """A wind model's floor is above this tender's price grid. The answer is the floor, said plainly."""
    from app.core.simulate import recommend

    rec = recommend(ladder, hurdle_tariff=3.59)
    assert rec.walk_away == pytest.approx(3.59)
    assert rec.entry_bid >= rec.walk_away and rec.target_low >= rec.walk_away and rec.target_high >= rec.walk_away
    assert any("above the price grid" in r for r in rec.reasons), rec.reasons
    for hurdle in (2.28, 2.60, 2.79):
        r = recommend(ladder, hurdle_tariff=hurdle)
        assert r.entry_bid >= r.walk_away - 1e-9 and r.target_low >= r.walk_away - 1e-9, hurdle
