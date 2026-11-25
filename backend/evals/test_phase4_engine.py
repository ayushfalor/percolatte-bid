"""Phase 4 gate: the price ladder is consistent with the RfS and with common sense."""
from __future__ import annotations

import time

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
    assert all(a >= b - 1e-12 for a, b in zip(odds, odds[1:]))


def test_extremes_make_sense(ladder):
    assert ladder[-1].p_win_any < 0.05 and ladder[0].p_win_any > 0.5
    assert all(0 <= p.expected_mw <= 200 for p in ladder)


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


def test_walk_away_is_the_stricter_of_irr_and_dscr(ladder):
    from app.core.simulate import recommend

    assert recommend(ladder, hurdle_tariff=2.28, dscr_tariff=2.10).walk_away == pytest.approx(2.28)
    assert recommend(ladder, hurdle_tariff=2.28, dscr_tariff=2.35).walk_away == pytest.approx(2.35)


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


def test_runtime_budget(snapshot, economics):
    from app.core.simulate import price_ladder

    t0 = time.perf_counter()
    price_ladder(snapshot, economics, seed=7)
    assert time.perf_counter() - t0 < 60
