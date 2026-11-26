"""Live auction, the key box, the plain-English tender and the scenario rerun.

The live read conditions the frozen rival draws on what the board shows; the tests check the
conditioning moves the odds the right way, never edits the snapshot, and gives the same answer
twice. The key box never writes a key anywhere but the local database.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

FACTS = json.loads((Path(__file__).parent / "expected" / "tender_facts.json").read_text())["facts"]


@pytest.fixture(scope="module")
def snapshot(samples):
    from app.core.history_reader import read_history
    from app.core.rival_model import build_snapshot

    return build_snapshot(read_history(str(samples / "auction_history.xlsx")), "almm_40", seed=42)


@pytest.fixture(scope="module")
def economics(bid_engine):
    rows = []
    for i in range(17):
        t = round(2.0 + i * 0.05, 2)
        v = bid_engine.evaluate({"Tariff": t}, ["Returns!C8", "Returns!C10"])
        rows.append({"tariff": t, "equity_irr": v["Returns!C8"], "min_dscr": v["Returns!C10"]})
    return rows


def _read(snapshot, economics, observations, our_price=2.45, **kw):
    from app.core.live_auction import live_read

    return live_read(snapshot, economics, 2.27, 2.20, observations, our_price, **kw)


def _at(ladder, tariff):
    return min(ladder, key=lambda p: abs(p.tariff - tariff))


# ---------- conditioning on the board ----------


def test_no_bids_is_the_war_room_ladder_with_a_caveat(snapshot, economics):
    read = _read(snapshot, economics, [])
    assert read.survivors == read.of == snapshot.n_draws and read.matched
    assert any("No bids typed in" in c for c in read.caveats)
    assert read.action in ("hold", "cut", "walk away") and len(read.ladder) == 81


def test_a_low_l1_lowers_our_odds_and_keeps_only_matching_auctions(snapshot, economics):
    from app.core.live_auction import L1, Observation

    base = _read(snapshot, economics, [])
    low = _read(snapshot, economics, [Observation(10, L1, 2.30)])
    assert 0 < low.survivors < low.of
    assert _at(low.ladder, 2.45).p_win_any <= _at(base.ladder, 2.45).p_win_any
    assert low.l1 == 2.30 and low.band_ceiling == 2.34 and low.in_band is False


def test_a_named_rival_is_in_and_ends_at_or_under_its_bid(snapshot, economics):
    from app.core.live_auction import Observation, matching
    from app.core.rival_model import draws

    name = snapshot.profiles[0].name
    arr = draws(snapshot)
    keep = matching(arr, [p.name for p in snapshot.profiles], {name: 2.44}, 2.45, None)
    assert keep.sum() > 0
    assert arr[keep][:, 0, 0].all() and (arr[keep][:, 0, 3] <= 2.44 + 1e-9).all()
    read = _read(snapshot, economics, [Observation(5, name, 2.44)])
    assert read.survivors == int(keep.sum())


def test_our_rank_means_that_many_rivals_end_under_us(snapshot, economics):
    from app.core.live_auction import matching
    from app.core.rival_model import draws

    arr = draws(snapshot)
    names = [p.name for p in snapshot.profiles]
    loose = matching(arr, names, {}, 2.45, 2)
    tight = matching(arr, names, {}, 2.45, 4)
    assert tight.sum() < loose.sum() <= len(arr)
    part, floors = arr[:, :, 0].astype(bool), arr[:, :, 3]
    assert ((part & (floors <= 2.45)).sum(axis=1)[tight] >= 3).all()


def test_a_rival_cutting_below_its_record_bends_the_draws_instead(snapshot, economics):
    from app.core.live_auction import Observation

    rival = max(snapshot.profiles, key=lambda p: p.p_participate)
    deep = rival.floor_p10 - 0.15
    read = _read(snapshot, economics, [Observation(12, rival.name, deep)], our_price=2.45)
    assert not read.matched and read.survivors < 200
    assert any("deeper than its record" in c for c in read.caveats)
    assert any(p.bidder == rival.name and p.below_record for p in read.pace)
    assert _at(read.ladder, 2.45).p_win_any <= _read(snapshot, economics, []).ladder[45].p_win_any


def test_the_snapshot_is_never_edited_and_the_answer_repeats(snapshot, economics):
    from app.core.live_auction import L1, Observation
    from app.core.rival_model import draws

    before = draws(snapshot).copy()
    obs = [Observation(3, L1, 2.40), Observation(9, snapshot.profiles[1].name, 2.42)]
    one, two = _read(snapshot, economics, obs), _read(snapshot, economics, obs)
    assert np.array_equal(before, draws(snapshot))
    assert one == two


# ---------- the advice ----------


def test_out_of_the_band_means_cut_to_a_price_inside_it(snapshot, economics):
    from app.core.live_auction import L1, Observation

    read = _read(snapshot, economics, [Observation(10, L1, 2.36)], our_price=2.45, minutes_left=20)
    assert read.in_band is False and read.action == "cut"
    assert read.cut_to is not None and read.cut_to <= read.band_ceiling + 1e-9
    assert read.cut_to >= read.recommendation.walk_away - 1e-9


def test_a_band_under_the_walk_away_means_walk(snapshot, economics):
    from app.core.live_auction import L1, Observation

    read = _read(snapshot, economics, [Observation(20, L1, 2.10)], our_price=2.30)
    assert read.action == "walk away"
    assert any("under the" in w and "walk-away" in w for w in read.why)


def test_in_the_band_with_time_left_means_hold(snapshot, economics):
    from app.core.live_auction import L1, Observation

    read = _read(snapshot, economics, [Observation(2, L1, 2.44)], our_price=2.45, minutes_left=25)
    assert read.in_band is True and read.action == "hold"
    assert read.best is not None and read.best.tariff <= 2.45 + 1e-9


def test_under_the_walk_away_already_means_stop(snapshot, economics):
    read = _read(snapshot, economics, [], our_price=2.20)
    assert read.action == "walk away" and "already under" in read.why[-3]


# ---------- pace ----------


def test_pace_reads_paise_per_minute_and_projects_the_close(snapshot, economics):
    from app.core.live_auction import Observation

    name = snapshot.profiles[2].name
    obs = [Observation(0, name, 2.60), Observation(10, name, 2.50)]
    read = _read(snapshot, economics, obs, minutes_left=10)
    pace = next(p for p in read.pace if p.bidder == name)
    assert pace.bids == 2 and pace.paise_per_minute == 1.0 and pace.projected_at_close == 2.40
    held = _read(snapshot, economics, obs, minutes_left=10, assume_pace_holds=True)
    assert any("Paces assumed" in c for c in held.caveats)
    assert _at(held.ladder, 2.45).p_win_any <= _at(read.ladder, 2.45).p_win_any


def test_the_sealed_stage_is_over_once_the_auction_runs(snapshot):
    from app.core import auction_rules as rules
    from app.core.rival_model import draws

    arr = draws(snapshot)
    live = rules.settle_field(arr[:, :, 0], arr[:, :, 3], arr[:, :, 1], arr[:, :, 2], 2.80, sealed_stage=False)
    assert not live["h1_eliminated"].any()
    sealed = rules.settle_field(arr[:, :, 0], arr[:, :, 3], arr[:, :, 1], arr[:, :, 2], 2.80)
    assert sealed["h1_eliminated"].any()


# ---------- the key box ----------


def test_env_lines_are_parsed_and_keys_are_recognised():
    from app.keys import KEY_PREFIX, looks_like_key, parse_env

    text = "# demo\nANTHROPIC_API_KEY='abc'\nLLM_MODEL_SMART=claude\n\nbroken line\n"
    assert parse_env(text) == {"ANTHROPIC_API_KEY": "abc", "LLM_MODEL_SMART": "claude"}
    assert looks_like_key(f"  {KEY_PREFIX}xyz ") and not looks_like_key("tkqmgg-nzsmaq")


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs the openssl binary")
def test_the_passphrase_unlocks_the_demo_key_and_a_wrong_one_does_not(tmp_path):
    from app.keys import KEY_PREFIX, unlock

    plain = tmp_path / ".env"
    plain.write_text(f"ANTHROPIC_API_KEY={KEY_PREFIX}demo-123\n")
    enc = tmp_path / "env.enc"
    subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-salt",
            "-in",
            str(plain),
            "-out",
            str(enc),
            "-pass",
            "pass:right",
        ],
        check=True,
    )
    assert unlock("right", enc) == f"{KEY_PREFIX}demo-123"
    assert unlock("wrong", enc) == ""


def test_the_environment_key_wins_and_no_database_means_offline(monkeypatch):
    from app import keys

    class Env:
        anthropic_api_key = " from-env "

    monkeypatch.setattr(keys, "get_settings", lambda: Env())
    assert keys.api_key() == "from-env" and keys.key_source() == "env" and keys.llm_mode() == "live"
    Env.anthropic_api_key = ""
    monkeypatch.setattr(keys, "stored_key", lambda: "")
    keys._cache = (0.0, "")
    assert keys.api_key() == "" and keys.key_source() == "none" and keys.llm_mode() == "offline"


# ---------- the project strip ----------


def test_the_plant_type_comes_from_the_models_own_words(samples, wind_workbook):
    from app.files import detect_technology

    assert detect_technology(str(samples / "bid_model.xlsx")) == "solar"
    assert detect_technology(str(wind_workbook[0])) == "wind"


# ---------- the tender in plain words ----------


def test_plain_summary_turns_the_facts_into_short_sections():
    from app.core.brief import must_dos
    from app.core.tender_plain import plain_summary

    sections = plain_summary(FACTS)
    headings = [s["heading"] for s in sections]
    assert headings == [
        "What is on offer",
        "Money we must put up",
        "How the auction works",
        "Deadlines",
        "What we promise",
    ]
    text = " ".join(s["text"] for s in sections)
    emd = must_dos(FACTS)["emd"]["cr"]
    assert "700 MW" in text and f"INR {emd:.1f} crore" in text and "clause 16.1" in text
    assert "30 minutes" in text and "2%" in text and "24 months" in text and "25%" in text
    odd = [{**f, "clause": "0.8"} if f["field"] == "se_cap_mw" else f for f in FACTS]
    assert "clause 0.8" not in " ".join(s["text"] for s in plain_summary(odd))


def test_every_unusual_clause_has_a_meaning():
    from app.core.tender_extract import UNUSUAL
    from app.core.tender_plain import GENERIC, MEANING, explain

    for rule in UNUSUAL:
        assert rule.field in MEANING, rule.field
        meaning = explain({"field": rule.field})
        assert meaning["title"] and meaning["what"] and meaning["for_us"]
    assert explain({"field": "something_new"}) == GENERIC


# ---------- over HTTP ----------


@pytest.mark.stack
def test_live_auction_over_http(api_client):
    doc = next(d for d in api_client.get("/api/documents").json() if d["filename"] == "bid_model.xlsx")
    body = {
        "observations": [{"minute": 5, "bidder": "L1", "tariff": 2.41}],
        "our_price": 2.45,
        "minutes_left": 20,
    }
    res = api_client.post(f"/api/live/{doc['id']}", json=body)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["action"] in ("hold", "cut", "walk away") and len(out["ladder"]) == 81
    assert out["l1"] == 2.41 and out["band_ceiling"] == 2.45 and out["in_band"] is True
    assert out["survivors"] <= out["of"] and out["why"]


@pytest.mark.stack
def test_the_key_box_refuses_a_wrong_phrase_and_stays_offline(api_client):
    state = api_client.get("/api/settings/llm").json()
    assert state["mode"] in ("offline", "live") and state["source"] in ("env", "saved", "none")
    if state["mode"] == "live":
        pytest.skip("a key is set in this stack")
    res = api_client.post("/api/settings/llm", json={"secret": "not-the-phrase"})
    assert res.status_code in (400, 409), res.text
    assert api_client.delete("/api/settings/llm").json()["mode"] == "offline"


@pytest.mark.stack
def test_tender_in_plain_words_over_http(api_client):
    out = api_client.get("/api/tender/plain").json()
    assert len(out["sections"]) >= 4 and out["unusual"]
    assert all(u["meaning"]["for_us"] for u in out["unusual"])


@pytest.mark.stack
def test_a_saved_scenario_can_be_rerun(api_client):
    doc = next(d for d in api_client.get("/api/documents").json() if d["filename"] == "bid_model.xlsx")
    sc = api_client.post(
        "/api/scenarios", json={"name": "test: capex -5%", "document_id": doc["id"], "overrides": {"Inputs!C7": 100}}
    ).json()
    run = api_client.post(f"/api/scenarios/{sc['id']}/run")
    assert run.status_code == 202 and run.json()["params"]["scenario_id"] == sc["id"]
