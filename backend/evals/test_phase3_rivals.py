"""Phase 3 gate: rival beliefs are sane, explained, reproducible and frozen."""

from __future__ import annotations

import hashlib
import statistics
from types import SimpleNamespace

import numpy as np
import pytest

pytestmark = pytest.mark.phase(3)
REGIMES = ("history", "almm_40", "almm_100")


@pytest.fixture(scope="module")
def history(samples):
    from app.core.history_reader import read_history

    return read_history(str(samples / "auction_history.xlsx"))


@pytest.fixture(scope="module")
def snapshots(history):
    from app.core.rival_model import build_snapshot

    return {regime: build_snapshot(history, regime, seed=42) for regime in REGIMES}


def test_same_seed_same_snapshot(history):
    from app.core.rival_model import build_snapshot

    a = build_snapshot(history, "almm_40", seed=42)
    b = build_snapshot(history, "almm_40", seed=42)
    assert a.sha256 == b.sha256
    assert build_snapshot(history, "almm_40", seed=43).sha256 != a.sha256, "a different seed is a different field"


def test_draws_rebuild_to_the_snapshot_hash(snapshots):
    """Frozen by construction: the draws come back from the seed and hash to the recorded value."""
    from app.core.rival_model import draws

    for snap in snapshots.values():
        arr = draws(snap)
        assert arr.shape == (snap.n_draws, len(snap.profiles), 4)
        assert hashlib.sha256(arr.tobytes()).hexdigest() == snap.sha256


def test_cheaper_panels_move_rival_floors_down(history):
    from app.core.rival_model import build_snapshot

    med = {
        r: statistics.median(p.floor_p50 for p in build_snapshot(history, r).profiles)
        for r in ("history", "almm_40", "almm_100")
    }
    assert med["history"] > med["almm_40"] > med["almm_100"]


def test_regime_shift_is_the_derived_pass_through(snapshots):
    """A-16: INR 14.5 to 10/Wp is worth about 0.37 INR/kWh; the regimes pass on 40% and 100% of it."""
    from app.core.rival_model import SHIFT_INR_PER_KWH

    base = {p.name: p.floor_p50 for p in snapshots["history"].profiles}
    for regime, share in (("almm_40", 0.4), ("almm_100", 1.0)):
        for p in snapshots[regime].profiles:
            assert base[p.name] - p.floor_p50 == pytest.approx(share * SHIFT_INR_PER_KWH, abs=1e-9), p.name


def test_every_rival_is_sane_and_explained(history):
    from app.core.rival_model import build_snapshot

    for p in build_snapshot(history, "almm_40").profiles:
        assert 0 <= p.p_participate <= 1
        assert 1.5 < p.floor_p10 <= p.floor_p50 <= p.floor_p90 < 3.5
        assert p.why and p.sources, p.name


def test_participation_matches_the_record(history, snapshots):
    """Chance to show up is tenders bid over tenders held, nothing more clever."""
    solar = history["solar_ists"]
    for p in snapshots["history"].profiles:
        stats = solar["groups"][p.name.upper()]
        assert p.p_participate == pytest.approx(len(stats["tenders"]) / solar["tenders"]), p.name


def test_archetypes_come_from_the_record(history, snapshots):
    """The one-off low bid in the history is read as a wildcard; a group that never won is a laggard."""
    solar = history["solar_ists"]
    lowest = min(f for s in solar["groups"].values() for f in s["final_tariffs"])
    by_name = {p.name.upper(): p for p in snapshots["history"].profiles}
    for name, stats in solar["groups"].items():
        p = by_name[name]
        if lowest in stats["final_tariffs"]:
            assert p.archetype == "wildcard", (name, stats["final_tariffs"])
        elif stats["wins"] == 0:
            assert p.archetype == "laggard", name
        else:
            assert p.archetype in {"leader", "mid_pack", "wildcard"}, name
    assert {p.archetype for p in by_name.values()} >= {"leader", "laggard"}, "a real field has both"


def test_draws_are_sane(snapshots):
    """What comes out of the generator matches what the profile says, draw by draw."""
    from app.core.rival_model import draws

    snap = snapshots["almm_40"]
    arr = draws(snap)
    for j, p in enumerate(snap.profiles):
        shows_up = arr[:, j, 0].mean()
        assert abs(shows_up - p.p_participate) < 0.03, (p.name, shows_up, p.p_participate)
        allowed = {mw for mw, _ in p.capacity_mw}
        assert set(np.unique(arr[:, j, 1])) <= allowed, p.name
        assert (arr[:, j, 2] > arr[:, j, 3]).all(), f"{p.name}: an opening bid must sit above the floor"
        inside = ((arr[:, j, 3] > p.floor_p10 - 0.25) & (arr[:, j, 3] < p.floor_p90 + 0.25)).mean()
        assert inside > 0.95, p.name


def test_every_profile_cites_its_tenders(history, snapshots):
    solar = history["solar_ists"]
    for p in snapshots["history"].profiles:
        tenders = solar["groups"][p.name.upper()]["tenders"]
        joined = " ".join(p.sources)
        assert all(t in joined for t in tenders), (p.name, p.sources)
        assert any("auction" in s.lower() for s in p.why), p.why


def test_unknown_regime_is_refused(history):
    from app.core.rival_model import build_snapshot

    with pytest.raises(ValueError):
        build_snapshot(history, "almm_70")


def test_rival_agent_returns_three_frozen_snapshots(samples):
    """The agent, driven with a stand-in context the way the worker would drive it."""
    from app.agents.rival import run
    from app.config import get_settings

    path = str(samples / "auction_history.xlsx")
    ctx = SimpleNamespace(
        params={},
        settings=get_settings(),
        document=lambda: (SimpleNamespace(kind="history", filename="auction_history.xlsx"), path),
        progress=lambda *_: None,
    )
    result = run(ctx)
    assert set(result["snapshots"]) == set(REGIMES)
    for regime, snap in result["snapshots"].items():
        assert snap["regime"] == regime and len(snap["sha256"]) == 64 and snap["profiles"]
