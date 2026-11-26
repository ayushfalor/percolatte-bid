"""Phase 7: the live e-RA. What the bids on the board say about the field, and what to do next.

The portal shows a bidder its own tariff and rank and the lowest tariff on the board (RfS §40.4);
market talk sometimes adds who is where. Either kind of line can be typed in here. Each one is a
constraint on the frozen rival draws, applied by rejection: a simulated auction is kept only when
it agrees with what was seen (D-013). The auctions that survive give a conditional price ladder
through the same settlement rules as the War Room, and the advice reads off that ladder.

Nothing here edits the snapshot. Same board, same seed, same answer.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import auction_rules as rules
from .contracts import LadderPoint, Recommendation, RivalProfile, RivalSnapshot
from .rival_model import draws
from .simulate import EXTENSION_MINUTES, ladder_from_arrays, point_value, recommend

L1 = "L1"  # the lowest tariff on the board, whoever holds it
MIN_SURVIVORS = 200  # fewer matching auctions than this and the draws no longer describe this field (A-25)
RECORD_GAP = 0.02  # INR/kWh under a rival's p10 floor counts as cutting below its record
CUT_GAIN = 0.02  # a cut has to buy at least this much more expected value than holding
MAX_PROJECTED_CUT = 0.30  # a pace is never projected more than 30 paise past the last bid (A-26)
HOLD, CUT, WALK = "hold", "cut", "walk away"
EPS = 1e-9


@dataclass(frozen=True)
class Observation:
    """One line typed in during the auction."""

    minute: int
    bidder: str  # a rival's name as the snapshot spells it, or L1
    tariff: float


@dataclass(frozen=True)
class Pace:
    bidder: str
    bids: int
    last_tariff: float
    paise_per_minute: float
    projected_at_close: float | None
    below_record: bool
    note: str


@dataclass(frozen=True)
class LiveRead:
    minutes_left: int
    l1: float | None
    band_ceiling: float | None
    in_band: bool | None
    survivors: int
    of: int
    matched: bool  # enough simulated auctions agree with the board to condition on it
    ladder: list[LadderPoint]
    recommendation: Recommendation
    action: str  # hold | cut | walk away
    cut_to: float | None
    at_our_price: LadderPoint
    best: LadderPoint | None
    why: list[str]
    pace: list[Pace]
    caveats: list[str]
    snapshot_id: str


def latest_by_bidder(observations: Iterable[Observation]) -> dict[str, Observation]:
    last: dict[str, Observation] = {}
    for o in sorted(observations, key=lambda o: o.minute):
        last[o.bidder] = o
    return last


def _pace_note(name: str, obs: list[Observation], per_minute: float, projected: float | None, known: bool) -> str:
    last = obs[-1]
    if len(obs) == 1:
        text = f"One bid so far, {last.tariff:.2f} at minute {last.minute}."
    elif per_minute <= 0:
        text = f"Holding at {last.tariff:.2f} since minute {obs[0].minute}."
    else:
        text = f"Cutting {per_minute * 100:.1f} paise a minute; about {projected:.2f} at the close if that holds."
    if not known and name != L1:
        text += " Not in the rival model, so read as the lowest price on the board."
    return text


def paces(observations: Iterable[Observation], minutes_left: int, profiles: list[RivalProfile]) -> list[Pace]:
    """How hard each bidder is cutting, from the lines typed in. Display first; a constraint only on request."""
    by_name = {p.name: p for p in profiles}
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for o in sorted(observations, key=lambda o: o.minute):
        grouped[o.bidder].append(o)
    out: list[Pace] = []
    for name, obs in grouped.items():
        first, last = obs[0], obs[-1]
        span, cut = last.minute - first.minute, first.tariff - last.tariff
        per_minute = cut / span if span > 0 and cut > 0 else 0.0
        projected = (
            round(max(last.tariff - min(per_minute * minutes_left, MAX_PROJECTED_CUT), 0.01), 2)
            if per_minute > 0
            else None
        )
        profile = by_name.get(name)
        below = profile is not None and last.tariff < profile.floor_p10 - RECORD_GAP
        note = _pace_note(name, obs, per_minute, projected, profile is not None)
        if below:
            note += f" That is under anything in its record (p10 floor {profile.floor_p10:.2f})."
        out.append(Pace(name, len(obs), last.tariff, round(per_minute * 100, 2), projected, below, note))
    return out


def _caps(last: dict[str, Observation], projected: dict[str, float]) -> dict[str, float]:
    """The most each observed bidder can end at: its last bid, or lower if its pace is assumed to hold."""
    return {name: min(obs.tariff, projected.get(name, obs.tariff)) for name, obs in last.items()}


def matching(arr: np.ndarray, names: list[str], caps: dict[str, float], our_price: float, our_rank: int | None):
    """Which simulated auctions agree with the board. A named rival is in and ends at or under its
    cap; an L1 or unknown line means some rival ends at or under it; rank r means r-1 rivals end under us."""
    part, floors = arr[:, :, 0].astype(bool), arr[:, :, 3]
    keep = np.ones(len(arr), dtype=bool)
    board = np.where(part, floors, np.inf).min(axis=1)
    for name, cap in caps.items():
        if name in names:
            j = names.index(name)
            keep &= part[:, j] & (floors[:, j] <= cap + EPS)
        else:
            keep &= board <= cap + EPS
    if our_rank is not None and our_rank > 1:
        keep &= (part & (floors <= our_price + EPS)).sum(axis=1) >= our_rank - 1
    return keep


def forced(arr: np.ndarray, names: list[str], caps: dict[str, float]) -> np.ndarray:
    """When too few auctions match, bend every draw instead: the named rival is in and stops no
    higher than its cap; an L1 line pulls the lowest rival of each draw down to it."""
    out = arr.copy()
    part, floors = out[:, :, 0], out[:, :, 3]
    rows = np.arange(len(out))
    for name, cap in caps.items():
        if name in names:
            j = names.index(name)
            part[:, j] = 1.0
            floors[:, j] = np.minimum(floors[:, j], cap)
            continue
        lowest = np.where(part > 0, floors, np.inf).argmin(axis=1)
        floors[rows, lowest] = np.minimum(floors[rows, lowest], cap)
    return out


def _band(last: dict[str, Observation], our_price: float) -> tuple[float | None, float | None, bool | None]:
    if not last:
        return None, None, None
    l1 = min(our_price, *(o.tariff for o in last.values()))
    ceiling = rules.band_ceiling(l1)
    return l1, ceiling, rules.truncate_paise(our_price) <= ceiling + EPS


def _advise(
    ladder: list[LadderPoint],
    rec: Recommendation,
    our_price: float,
    minutes_left: int,
    ceiling: float | None,
    in_band: bool | None,
) -> tuple[str, float | None, LadderPoint | None, LadderPoint, list[str]]:
    walk = rec.walk_away
    at_now = min(ladder, key=lambda p: abs(p.tariff - our_price))
    reach = [p for p in ladder if walk - EPS <= p.tariff <= our_price + EPS]
    best = max(reach, key=lambda p: point_value(p, walk)) if reach else None
    why: list[str] = []
    if our_price < walk - EPS:
        why.append(f"Our {our_price:.2f} is already under the {walk:.2f} walk-away. Stop cutting.")
        return WALK, None, best, at_now, why
    if ceiling is not None and ceiling < walk - EPS:
        why.append(f"Staying in the band needs {ceiling:.2f} or less, under the {walk:.2f} walk-away. Let it go.")
        return WALK, None, best, at_now, why
    if best is None or point_value(best, walk) <= 0:
        why.append(
            f"No price between the {walk:.2f} walk-away and our {our_price:.2f} wins in the auctions on this board."
        )
        return WALK, None, best, at_now, why
    if in_band is False:
        in_band_reach = [p for p in reach if ceiling is not None and p.tariff <= ceiling + EPS]
        to = max(in_band_reach, key=lambda p: point_value(p, walk)).tariff if in_band_reach else ceiling
        why.append(f"Out of the band: above {ceiling:.2f} nothing wins if the auction ended now. Cut to {to:.2f}.")
        return CUT, to, best, at_now, why
    gain = point_value(best, walk) > max(point_value(at_now, walk), 0.0) * (1 + CUT_GAIN)
    if minutes_left <= EXTENSION_MINUTES and best.tariff < our_price - 0.005 and gain:
        why.append(
            f"{minutes_left} minutes left and {best.tariff:.2f} carries more expected value than holding at "
            f"{our_price:.2f}. Cut to {best.tariff:.2f}."
        )
        return CUT, best.tariff, best, at_now, why
    why.append(
        f"In the band with {minutes_left} minutes left. Best final price given the board: {best.tariff:.2f}; "
        f"be ready to cut to it, never under {walk:.2f}."
    )
    return HOLD, None, best, at_now, why


def live_read(
    snapshot: RivalSnapshot,
    economics: list[dict[str, Any]],
    hurdle_tariff: float,
    dscr_tariff: float | None,
    observations: list[Observation],
    our_price: float,
    minutes_left: int = 30,
    our_rank: int | None = None,
    assume_pace_holds: bool = False,
    our_mw: float = 200,
    tendered_mw: float = 700,
) -> LiveRead:
    """The board, read against the rival draws: conditional ladder, the three numbers, and the next move."""
    arr = draws(snapshot)
    names = [p.name for p in snapshot.profiles]
    last = latest_by_bidder(observations)
    pace = paces(observations, minutes_left, list(snapshot.profiles))
    projected = {p.bidder: p.projected_at_close for p in pace if p.projected_at_close is not None}
    caps = _caps(last, projected if assume_pace_holds else {})
    keep = matching(arr, names, caps, our_price, our_rank)
    survivors, matched = int(keep.sum()), bool(keep.sum() >= MIN_SURVIVORS)
    caveats: list[str] = []
    if matched:
        sub = arr[keep]
    else:
        sub = forced(arr, names, caps)
        caveats.append(
            f"Only {survivors} of {len(arr):,} simulated auctions match this board: the field is cutting "
            "deeper than its record. Every rival named is now taken to stop no higher than its last bid."
        )
    if not observations:
        caveats.append("No bids typed in yet, so this is the War Room's own ladder.")
    if assume_pace_holds and projected:
        caveats.append("Paces assumed to hold: each cutting rival is taken to reach its projected price (A-26).")
    ladder = ladder_from_arrays(
        sub[:, :, 0], sub[:, :, 1], sub[:, :, 2], sub[:, :, 3], economics, our_mw, tendered_mw, sealed_stage=False
    )
    rec = recommend(ladder, hurdle_tariff=hurdle_tariff, dscr_tariff=dscr_tariff)
    l1, ceiling, in_band = _band(last, our_price)
    action, cut_to, best, at_now, why = _advise(ladder, rec, our_price, minutes_left, ceiling, in_band)
    if l1 is not None:
        why.insert(0, f"L1 on the board {l1:.2f}; anything above {ceiling:.2f} cannot win (L1 + 2%, cut to paise).")
    why.append(
        f"At {at_now.tariff:.2f}: {at_now.p_win_any:.0%} chance of winning something, "
        f"{at_now.expected_mw:.0f} MW expected, in the {len(sub):,} auctions used."
    )
    why.append(rec.reasons[0])
    return LiveRead(
        minutes_left=minutes_left,
        l1=l1,
        band_ceiling=ceiling,
        in_band=in_band,
        survivors=survivors,
        of=len(arr),
        matched=matched,
        ladder=ladder,
        recommendation=rec,
        action=action,
        cut_to=cut_to,
        at_our_price=at_now,
        best=best,
        why=why,
        pace=pace,
        caveats=caveats,
        snapshot_id=snapshot.id,
    )
