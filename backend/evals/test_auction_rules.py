"""The RfS's own worked examples are the ground truth for the auction rules."""
from __future__ import annotations

from app.core import auction_rules as r


def test_band_truncates_to_paise():
    assert r.band_ceiling(1.65) == 1.68  # §41.3 illustration
    assert r.band_ceiling(2.50) == 2.55
    assert r.truncate_paise(1.637) == 1.63  # §39.3


def test_eligible_capacity_rule():
    assert r.eligible_capacity(2750) == 700  # §40.2 scenario 1
    assert r.eligible_capacity(700) == 560  # §40.2 scenario 2
    assert r.eligible_capacity(800) == 640  # oversubscribed but 0.8 x ST < 700: less than 700 awarded


def test_rfs_40_2_scenario_1_eliminates_h1():
    bids = [r.Bid(b, cap, t) for b, cap, t in [
        ("B8", 600, 1.50), ("B5", 300, 1.52), ("B1", 300, 1.53), ("B4", 250, 1.53),
        ("B2", 300, 1.57), ("B3", 500, 1.60), ("B7", 200, 1.65), ("B6", 300, 1.71)]]
    s = r.shortlist_for_era(bids)
    assert (s.total_bidders, s.total_bid_mw, s.eligible_mw) == (8, 2750, 700)
    assert s.eliminated == ["B6"] and len(s.shortlisted) == 7
    assert s.ranks["B1"] == s.ranks["B4"] == 3 and s.ranks["B6"] == 7  # ties share a rank


def test_rfs_40_2_scenario_2_no_elimination():
    bids = [r.Bid("B3", 100, 1.50), r.Bid("B2", 300, 1.52), r.Bid("B1", 100, 1.53), r.Bid("B4", 200, 1.55)]
    s = r.shortlist_for_era(bids)
    assert s.eligible_mw == 560 and s.eliminated == [] and len(s.shortlisted) == 4


def test_no_elimination_when_h1_is_tied():
    bids = [r.Bid("A", 600, 2.4), r.Bid("B", 500, 2.5), r.Bid("C", 300, 2.6), r.Bid("D", 300, 2.6)]
    assert r.shortlist_for_era(bids).eliminated == []


def test_no_elimination_when_it_would_undersubscribe():
    bids = [r.Bid("A", 400, 2.4), r.Bid("B", 400, 2.5), r.Bid("C", 100, 2.6)]  # 0.8 x 900 = 720, minus H1 = 640
    assert r.shortlist_for_era(bids).eliminated == []


def test_no_elimination_below_three_bidders():
    bids = [r.Bid("A", 700, 2.4), r.Bid("B", 700, 2.5), r.Bid("C", 700, 2.6)]
    assert r.shortlist_for_era(bids).eliminated == []


def test_rfs_41_3_illustration():
    bids = [r.Bid("L1", 50, 1.65), r.Bid("L2", 150, 1.66), r.Bid("L3a", 200, 1.68, 1), r.Bid("L3b", 300, 1.68, 2),
            r.Bid("L3c", 50, 1.68, 3), r.Bid("L4", 200, 1.70), r.Bid("L5", 100, 1.71)]
    a = r.allocate(bids, 700)
    assert a.l1 == 1.65 and a.band_ceiling == 1.68 and a.awarded_mw == 700
    assert [w.bidder for w in a.awards if w.awarded_mw > 0] == ["L1", "L2", "L3a", "L3b"]
    assert a.for_bidder("L3c").zone == "red"  # same tariff, later time stamp
    assert a.for_bidder("L4").zone == "red"  # outside L1 + 2%


def test_partial_award_rules():
    a = r.allocate([r.Bid("A", 500, 2.40), r.Bid("B", 300, 2.41)], 700)
    b = a.for_bidder("B")
    assert (b.zone, b.awarded_mw, b.refusable) == ("orange", 200, False)  # 200/300 >= 50%: must accept
    a = r.allocate([r.Bid("A", 600, 2.40), r.Bid("B", 300, 2.41)], 700)
    assert (a.for_bidder("B").awarded_mw, a.for_bidder("B").refusable) == (100, True)  # 100/300 < 50%: may refuse
    a = r.allocate([r.Bid("A", 660, 2.40), r.Bid("B", 300, 2.41)], 700)
    assert a.for_bidder("B").zone == "red"  # only 40 MW left, below the 50 MW minimum


def test_aggressive_l1_locks_others_out():
    """Under the 2% band one aggressive bidder can leave capacity unawarded (MOCK-2026-036 pattern)."""
    a = r.allocate([r.Bid("Wild", 500, 2.36), r.Bid("A", 300, 2.49), r.Bid("B", 400, 2.50)], 700)
    assert a.band_ceiling == 2.40 and a.awarded_mw == 500


def test_eighty_percent_rule_and_h1_knockout_never_happen_together():
    # 0.8 x 870 = 696 MW <= 700: nobody is knocked out, but only 696 MW can be awarded
    s = r.shortlist_for_era([r.Bid("A", 300, 2.40), r.Bid("B", 300, 2.50), r.Bid("C", 270, 2.60)])
    assert s.eligible_mw == 696 and s.eliminated == []
    # 0.8 x 1200 = 960 MW > 700: the full 700 MW is awarded and the single highest bidder goes
    s = r.shortlist_for_era([r.Bid("A", 400, 2.40), r.Bid("B", 300, 2.50), r.Bid("C", 300, 2.55), r.Bid("D", 200, 2.60)])
    assert s.eligible_mw == 700 and s.eliminated == ["D"]


def test_partial_award_cliffs_for_a_200_mw_bid():
    cases = [(590, "orange", 110, False),  # 110 MW is at least half of 200: must accept or lose the EMD
             (620, "orange", 80, True),    # 80 MW is under half: may refuse, EMD returned
             (660, "red", 0, False)]       # only 40 MW left: below the 50 MW minimum, nothing awarded
    for cheaper_mw, zone, mw, refusable in cases:
        a = r.allocate([r.Bid("Rival", cheaper_mw, 2.40), r.Bid("Us", 200, 2.41)], 700).for_bidder("Us")
        assert (a.zone, a.awarded_mw, a.refusable) == (zone, mw, refusable), cheaper_mw
