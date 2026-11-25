"""SECI e-Reverse Auction rules, RfS No. SECI/C&P/IPP/15/0009/26-27 (C&I-1).

Pure functions, no I/O, no randomness. Each rule names the clause it
implements so the eval suite can check it against the RfS's own worked
examples (§40.2 scenarios 1 and 2, §41.3 illustration).

Simplification (documented in ASSUMPTIONS.md): each bidder is one block of
capacity. The RfS lets a bidder split capacity into several projects with a
preference order; we round a partial award down to 10 MW instead.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

Zone = Literal["green", "orange", "red"]

ELIGIBLE_SHARE = 0.8  # §40.2: SE = 0.8 x ST
BAND = 0.02  # §41.2: L1 + 2% of L1
MIN_PROJECT_MW = 50  # §41.3 note: no project below 50 MW
STEP_MW = 10  # §5.1: capacity in multiples of 10 MW
MIN_SHORTLIST = 3  # §40.2 note (b)


def truncate_paise(x: float) -> float:
    """§39.3: digits after two decimals are ignored (1.637 -> 1.63)."""
    return math.floor(round(x * 100, 6)) / 100


def band_ceiling(l1: float) -> float:
    """Highest tariff that can still win: L1 + 2%, truncated (1.65 -> 1.68)."""
    return truncate_paise(l1 * (1 + BAND))


def eligible_capacity(total_bid_mw: float, tendered_mw: float = 700) -> float:
    """§40.2: SE = 0.8 x ST, never more than the tendered capacity."""
    return min(ELIGIBLE_SHARE * total_bid_mw, tendered_mw)


@dataclass(frozen=True)
class Bid:
    bidder: str
    capacity_mw: float
    tariff: float  # first-round tariff for shortlisting, last e-RA quote for allocation
    timestamp: float = 0.0  # time of last e-RA quote; earlier wins ties (§41.2.c)
    first_round_tariff: float | None = None  # tie-break step 1 (§41.2.d)


@dataclass
class Shortlist:
    total_bidders: int  # T
    total_bid_mw: float  # ST
    eligible_mw: float  # SE
    ranks: dict[str, int]  # dense ranks, ties share a rank (§39.6, §39.8)
    eliminated: list[str]
    shortlisted: list[str]
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def rank_bids(bids: list[Bid]) -> dict[str, int]:
    """Dense ranking on tariff: 1.50 L1, 1.52 L2, 1.53 L3, 1.53 L3, 1.57 L4 (§39.8)."""
    levels = sorted({truncate_paise(b.tariff) for b in bids})
    level_rank = {t: i + 1 for i, t in enumerate(levels)}
    return {b.bidder: level_rank[truncate_paise(b.tariff)] for b in bids}


def shortlist_for_era(bids: list[Bid], tendered_mw: float = 700) -> Shortlist:
    """§40.2: compute SE and decide whether the H1 bidder is eliminated."""
    if not bids:
        raise ValueError("No bids")
    st = sum(b.capacity_mw for b in bids)
    se = eligible_capacity(st, tendered_mw)
    ranks = rank_bids(bids)
    everyone = [b.bidder for b in sorted(bids, key=lambda b: (truncate_paise(b.tariff), b.bidder))]

    if ELIGIBLE_SHARE * st <= tendered_mw:
        return Shortlist(len(bids), st, se, ranks, [], everyone, "0.8 x ST <= tendered capacity: no elimination")

    highest = max(truncate_paise(b.tariff) for b in bids)
    h1 = [b for b in bids if truncate_paise(b.tariff) == highest]
    if len(h1) > 1:
        return Shortlist(len(bids), st, se, ranks, [], everyone, "More than one H1 bidder: no elimination (note a)")

    h1_bid = h1[0]
    remaining_mw = st - h1_bid.capacity_mw
    if ELIGIBLE_SHARE * remaining_mw <= tendered_mw:
        return Shortlist(len(bids), st, se, ranks, [], everyone,
                         "Eliminating H1 would drop 0.8 x capacity below tendered: no elimination (note b)")
    if len(bids) - 1 < MIN_SHORTLIST:
        return Shortlist(len(bids), st, se, ranks, [], everyone,
                         "Fewer than 3 bidders would remain: no elimination (note b)")

    kept = [name for name in everyone if name != h1_bid.bidder]
    return Shortlist(len(bids), st, se, ranks, [h1_bid.bidder], kept, "H1 bidder eliminated")


@dataclass
class Award:
    bidder: str
    tariff: float
    capacity_mw: float
    zone: Zone
    awarded_mw: float
    refusable: bool  # §41.4: partial award below 50% of quoted capacity may be refused
    reason: str


@dataclass
class Allocation:
    l1: float
    band_ceiling: float
    eligible_mw: float
    awarded_mw: float
    awards: list[Award] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def for_bidder(self, bidder: str) -> Award | None:
        return next((a for a in self.awards if a.bidder == bidder), None)


def _order_key(b: Bid) -> tuple:
    # §41.2.c time stamp, then §41.2.d first-round tariff, then name (stands in for the draw of lots)
    first = b.first_round_tariff if b.first_round_tariff is not None else math.inf
    return (truncate_paise(b.tariff), b.timestamp, first, b.bidder)


def allocate(bids: list[Bid], eligible_mw: float) -> Allocation:
    """§40.4.vi zones and §41 bucket filling. Works for the live board or the final state."""
    if not bids:
        raise ValueError("No bids")
    ordered = sorted(bids, key=_order_key)
    l1 = truncate_paise(ordered[0].tariff)
    ceiling = band_ceiling(l1)
    filled = 0.0
    out = Allocation(l1=l1, band_ceiling=ceiling, eligible_mw=eligible_mw, awarded_mw=0.0)
    for b in ordered:
        tariff = truncate_paise(b.tariff)
        remaining = eligible_mw - filled
        if tariff > ceiling + 1e-9:
            out.awards.append(Award(b.bidder, tariff, b.capacity_mw, "red", 0.0, False,
                                    f"Above L1 + 2% ({ceiling:.2f})"))
            continue
        if remaining <= 1e-9:
            out.awards.append(Award(b.bidder, tariff, b.capacity_mw, "red", 0.0, False, "Eligible capacity already filled"))
            continue
        if b.capacity_mw <= remaining + 1e-9:
            filled += b.capacity_mw
            out.awards.append(Award(b.bidder, tariff, b.capacity_mw, "green", b.capacity_mw, False, "Full award"))
            continue
        partial = math.floor(remaining / STEP_MW) * STEP_MW
        if partial >= MIN_PROJECT_MW:
            filled += partial
            refusable = partial < 0.5 * b.capacity_mw
            out.awards.append(Award(b.bidder, tariff, b.capacity_mw, "orange", partial, refusable,
                                    "Partial award" + (" (may refuse, below 50%)" if refusable else " (must accept, 50% or more)")))
        else:
            out.awards.append(Award(b.bidder, tariff, b.capacity_mw, "red", 0.0, False,
                                    f"Only {remaining:.0f} MW left, below the 50 MW minimum"))
    out.awarded_mw = filled
    return out
