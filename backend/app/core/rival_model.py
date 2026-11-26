"""Phase 3: rival beliefs as frozen snapshots.

Regimes (each one its own frozen snapshot, so a UI switch never edits beliefs):
  history   rivals bid like the last 13 solar ISTS auctions
  almm_40   rivals pass on 40% of the imported-panel saving
  almm_100  rivals pass on all of it

Everything here is calibrated on the cleaned auction history (history_reader.solar_ists) and
written down: every profile carries a `why` in plain English and the tenders it rests on. The
draws come from a seeded generator, so the same seed always gives the same snapshot, and the
snapshot's sha256 is taken over the draws themselves.
"""

from __future__ import annotations

import hashlib
import statistics
from typing import Any

import numpy as np

from .contracts import RivalProfile, RivalSnapshot

REGIMES = {"history": 0.0, "almm_40": 0.4, "almm_100": 1.0}  # share of the module saving passed on
SHIFT_INR_PER_KWH = 0.37  # A-16: INR 14.5 to 10/Wp at about 0.082 INR/kWh per INR/Wp
MARKET_SD = 0.03  # one shared move per draw, so rivals move together
SURPRISE_P = 0.05  # a one-off aggressive bidder, like INR 2.36 in MOCK-2026-036
SURPRISE_CUT = 0.10
WILDCARD_GAP = 0.05  # a floor this far under the typical L1 marks a wildcard
LEADER_WIN_RATE = 0.5
Z80 = 1.2816  # p10 and p90 sit this many standard deviations from the median
MIN_SPREAD = 0.02  # never claim to know a rival's floor tighter than two paise


def _archetype(stats: dict[str, Any], typical_l1: float) -> str:
    plays = len(stats["tenders"])
    if plays == 0:
        return "laggard"
    if stats["final_tariffs"] and min(stats["final_tariffs"]) < typical_l1 - WILDCARD_GAP:
        return "wildcard"
    if stats["wins"] / plays >= LEADER_WIN_RATE and stats["at_l1"] > 0:
        return "leader"
    return "laggard" if stats["wins"] == 0 else "mid_pack"


def _floors(finals: list[float], typical_l1: float, field_sd: float) -> tuple[float, float, float]:
    """Where a rival stops cutting. Few observations widen the band, never narrow it."""
    if not finals:
        return typical_l1 - Z80 * field_sd, typical_l1, typical_l1 + Z80 * field_sd
    p50 = statistics.median(finals)
    own_sd = statistics.pstdev(finals) if len(finals) > 1 else field_sd
    sd = max(own_sd, field_sd if len(finals) < 3 else MIN_SPREAD / Z80, MIN_SPREAD / Z80)
    return p50 - Z80 * sd, p50, p50 + Z80 * sd


def _capacity(quoted: list[float]) -> list[tuple[float, float]]:
    if not quoted:
        return [(100.0, 1.0)]
    counts: dict[float, int] = {}
    for mw in quoted:
        counts[mw] = counts.get(mw, 0) + 1
    total = sum(counts.values())
    return sorted((mw, n / total) for mw, n in counts.items())


def _profile(name: str, stats: dict[str, Any], solar: dict[str, Any], shift: float) -> RivalProfile:
    plays, n_tenders = len(stats["tenders"]), max(solar["tenders"], 1)
    l1s = list(solar["l1_tariffs"].values())
    typical_l1 = statistics.median(l1s) if l1s else 2.5
    field_sd = statistics.pstdev(l1s) if len(l1s) > 1 else 0.05
    p10, p50, p90 = (f - shift for f in _floors(stats["final_tariffs"], typical_l1, field_sd))
    archetype = _archetype(stats, typical_l1)
    why = [
        f"Bid in {plays} of {n_tenders} solar ISTS auctions, won {stats['wins']}, "
        f"finished at L1 {stats['at_l1']} times.",
        (
            f"Final tariffs ran from {min(stats['final_tariffs']):.2f} to {max(stats['final_tariffs']):.2f}."
            if stats["final_tariffs"]
            else "Never reached the e-RA, so the floor is the field's, not its own."
        ),
        f"Read as {archetype.replace('_', ' ')} on that record.",
    ]
    if shift:
        why.append(f"Floor moved down {shift:.2f} INR/kWh for the module saving passed on in this regime (A-16).")
    return RivalProfile(
        name=name.title(),
        archetype=archetype,
        p_participate=plays / n_tenders,
        capacity_mw=_capacity(stats["quoted_mw"]),
        floor_p10=p10,
        floor_p50=p50,
        floor_p90=p90,
        why=why,
        sources=[
            f"auction_history.xlsx: {', '.join(stats['tenders'])}" if stats["tenders"] else "auction_history.xlsx"
        ],
    )


def _draw_array(profiles: list[RivalProfile], seed: int, n_draws: int) -> np.ndarray:
    """Joint draws, one row per auction: [participates, MW, opening bid, floor] per rival."""
    rng = np.random.default_rng(seed)
    n = len(profiles)
    market = rng.normal(0.0, MARKET_SD, size=(n_draws, 1))
    surprise = rng.random((n_draws, n)) < SURPRISE_P
    out = np.zeros((n_draws, n, 4))
    for j, p in enumerate(profiles):
        out[:, j, 0] = rng.random(n_draws) < p.p_participate
        mws, probs = zip(*p.capacity_mw, strict=True)
        out[:, j, 1] = rng.choice(mws, size=n_draws, p=np.array(probs) / sum(probs))
        sd = max((p.floor_p90 - p.floor_p10) / (2 * Z80), MIN_SPREAD / Z80)
        floor = p.floor_p50 + market[:, 0] + rng.normal(0.0, sd, n_draws) - SURPRISE_CUT * surprise[:, j]
        out[:, j, 3] = floor
        out[:, j, 2] = floor + rng.uniform(0.03, 0.12, n_draws)  # the opening sits above the floor
    return out


def build_snapshot(
    history: dict[str, Any],
    regime: str,
    seed: int = 42,
    n_draws: int = 5000,
    dossiers: list[dict[str, Any]] | None = None,
) -> RivalSnapshot:
    """A frozen set of beliefs about the field, for one regime. Same seed, same snapshot."""
    if regime not in REGIMES:
        raise ValueError(f"Unknown regime {regime!r}; one of {', '.join(REGIMES)}")
    solar = history["solar_ists"]
    shift = REGIMES[regime] * SHIFT_INR_PER_KWH
    profiles = [_profile(name, stats, solar, shift) for name, stats in sorted(solar["groups"].items())]
    digest = hashlib.sha256(_draw_array(profiles, seed, n_draws).tobytes()).hexdigest()
    return RivalSnapshot(
        id=f"{regime}-s{seed}-{digest[:8]}",
        regime=regime,
        seed=seed,
        n_draws=n_draws,
        profiles=profiles,
        sha256=digest,
    )


def draws(snapshot: RivalSnapshot) -> np.ndarray:
    """The joint draws, rebuilt from the seed. Read-only: the array always hashes to snapshot.sha256."""
    return _draw_array(list(snapshot.profiles), snapshot.seed, snapshot.n_draws)
