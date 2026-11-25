"""Phase 3 gate: rival beliefs are sane, explained, reproducible and frozen."""

from __future__ import annotations

import statistics

import pytest

pytestmark = pytest.mark.phase(3)


@pytest.fixture(scope="module")
def history(samples):
    from app.core.history_reader import read_history

    return read_history(str(samples / "auction_history.xlsx"))


def test_same_seed_same_snapshot(history):
    from app.core.rival_model import build_snapshot

    a = build_snapshot(history, "almm_40", seed=42)
    b = build_snapshot(history, "almm_40", seed=42)
    assert a.sha256 == b.sha256


def test_cheaper_panels_move_rival_floors_down(history):
    from app.core.rival_model import build_snapshot

    med = {
        r: statistics.median(p.floor_p50 for p in build_snapshot(history, r).profiles)
        for r in ("history", "almm_40", "almm_100")
    }
    assert med["history"] > med["almm_40"] > med["almm_100"]


def test_every_rival_is_sane_and_explained(history):
    from app.core.rival_model import build_snapshot

    for p in build_snapshot(history, "almm_40").profiles:
        assert 0 <= p.p_participate <= 1
        assert 1.5 < p.floor_p10 <= p.floor_p50 <= p.floor_p90 < 3.5
        assert p.why and p.sources, p.name
