"""Phase 4: Monte Carlo price ladder, recommendation and replay.

Every rule of the auction goes through core.auction_rules. The ladder uses its vectorised
settlement over the frozen rival draws; the replay uses the scalar functions tick by tick. The
profit side comes from the economics curve the Engine agent already computes from the workbook,
interpolated here; the workbook is never called from this module.

Same draws for every price (common random numbers), so differences between prices or scenarios
come from inputs, not luck.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import auction_rules as rules
from .contracts import LadderPoint, Recommendation, RivalSnapshot
from .rival_model import draws

TYPICAL_CUT = 0.08  # INR/kWh from sealed bid to final price, the history's median
INITIAL_MINUTES = 30  # §40.4
EXTENSION_MINUTES = 8  # §40.4, on a zone change in the last 8 minutes
MAX_MINUTES = 240
TARGET_SHARE = 0.9  # the target range is every price within this share of the best expected value


def _curve(economics: list[dict[str, Any]], key: str):
    rows = sorted((r for r in economics if isinstance(r.get(key), (int, float))), key=lambda r: r["tariff"])
    if not rows:
        return None
    xs = np.array([r["tariff"] for r in rows], dtype=float)
    ys = np.array([r[key] for r in rows], dtype=float)
    return lambda t: float(np.interp(t, xs, ys))


def price_ladder(
    snapshot: RivalSnapshot,
    economics: list[dict[str, Any]],
    our_mw: float = 200,
    tendered_mw: float = 700,
    start: float = 2.00,
    stop: float = 2.80,
    step: float = 0.01,
    seed: int = 42,
) -> list[LadderPoint]:
    """Win odds (from the rival draws) joined with profit (from the workbook) at every price.

    economics rows: {"tariff", "equity_irr", "min_dscr", optional "npv_cr"}, as produced by the
    Engine agent's economics curve. Interpolate between rows; never call the workbook here.
    `seed` is accepted for symmetry with the snapshot; the draws are the snapshot's own.
    """
    arr = draws(snapshot)
    part, mw, opens, floors = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    irr, dscr, npv = _curve(economics, "equity_irr"), _curve(economics, "min_dscr"), _curve(economics, "npv_cr")
    ladder: list[LadderPoint] = []
    for tariff in np.round(np.arange(start, stop + step / 2, step), 2):
        price = float(tariff)
        settled = rules.settle_field(part, floors, mw, opens, price, our_mw, tendered_mw)
        win = settled["win_mw"]
        expected_mw = float(win.mean())
        value = npv(price) if npv else None
        ladder.append(
            LadderPoint(
                tariff=price,
                p_win_any=float((win > 0).mean()),
                p_win_full=float((win >= our_mw - 1e-9).mean()),
                expected_mw=expected_mw,
                p_h1_eliminated=float(settled["h1_eliminated"].mean()),
                equity_irr=irr(price) if irr else None,
                min_dscr=dscr(price) if dscr else None,
                npv_cr=value,
                expected_value_cr=(expected_mw / our_mw * value) if value is not None else None,
            )
        )
    return ladder


def recommend(
    ladder: list[LadderPoint], hurdle_tariff: float, dscr_tariff: float | None = None, max_h1_risk: float = 0.05
) -> Recommendation:
    """walk_away = max(hurdle_tariff, dscr_tariff); target band = best expected value above it."""
    walk_away = max(hurdle_tariff, dscr_tariff or 0.0)
    above = [p for p in ladder if p.tariff >= walk_away - 1e-9] or [max(ladder, key=lambda p: p.tariff)]

    def value(p: LadderPoint) -> float:
        # Expected value if the workbook gave one; else expected MW times margin over the floor.
        return p.expected_value_cr if p.expected_value_cr is not None else p.expected_mw * (p.tariff - walk_away)

    best = max(value(p) for p in above)
    band = [p for p in above if value(p) >= TARGET_SHARE * best] if best > 0 else above[:1]
    target_low, target_high = min(p.tariff for p in band), max(p.tariff for p in band)

    safe = [p for p in above if p.tariff >= walk_away + TYPICAL_CUT - 1e-9 and p.p_h1_eliminated <= max_h1_risk]
    entry = min(safe, key=lambda p: p.tariff) if safe else min(above, key=lambda p: (p.p_h1_eliminated, p.tariff))
    reasons = [
        f"Walk-away {walk_away:.2f}: the stricter of the {hurdle_tariff:.2f} hurdle tariff"
        + (f" and the {dscr_tariff:.2f} DSCR tariff." if dscr_tariff else "."),
        f"Target {target_low:.2f} to {target_high:.2f}: "
        f"within {TARGET_SHARE:.0%} of the best expected value above the floor.",
        f"Entry {entry.tariff:.2f}: room for the typical {TYPICAL_CUT * 100:.0f} paise cut, "
        f"{entry.p_h1_eliminated:.1%} chance of going out as H1.",
    ]
    return Recommendation(
        entry_bid=entry.tariff, target_low=target_low, target_high=target_high, walk_away=walk_away, reasons=reasons
    )


def replay(
    snapshot: RivalSnapshot, draw_index: int, our_open: float, our_floor: float, our_mw: float = 200
) -> list[dict[str, Any]]:
    """Tick-by-tick e-RA for the war room: 1 paisa cuts, 30 min + 8 min extensions on zone change."""
    arr = draws(snapshot)[draw_index]
    names = [p.name for p in snapshot.profiles]
    field = {
        name: {"mw": float(arr[j, 1]), "price": rules.truncate_paise(float(arr[j, 2])), "floor": float(arr[j, 3])}
        for j, name in enumerate(names)
        if arr[j, 0] > 0
    }
    field["Us"] = {"mw": our_mw, "price": rules.truncate_paise(our_open), "floor": our_floor}
    total = sum(b["mw"] for b in field.values())
    eligible = rules.eligible_capacity(total)
    stamps = dict.fromkeys(field, 0.0)

    def zones() -> dict[str, str]:
        bids = [rules.Bid(n, b["mw"], b["price"], stamps[n]) for n, b in field.items()]
        return {a.bidder: a.zone for a in rules.allocate(bids, eligible).awards}

    events: list[dict[str, Any]] = [{"minute": 0, "type": "open", "eligible_mw": eligible, "bidders": len(field)}]
    end = INITIAL_MINUTES
    minute = 1
    zone = zones()
    while minute <= min(end, MAX_MINUTES):
        moved = False
        for name, b in field.items():
            if zone.get(name) == "green" or b["price"] - 0.01 < b["floor"] - 1e-9:
                continue
            new = rules.truncate_paise(b["price"] - 0.01)
            events.append({"minute": minute, "type": "bid", "bidder": name, "old": b["price"], "new": new})
            b["price"], stamps[name], moved = new, float(minute), True
        new_zone = zones()
        if new_zone != zone and minute > end - EXTENSION_MINUTES:
            end = max(end, minute + EXTENSION_MINUTES)  # §40.4: eight minutes from the move, not from the old end
            events.append({"minute": minute, "type": "extension", "until": end})
        zone = new_zone
        if not moved:
            break
        minute += 1
    final = rules.allocate([rules.Bid(n, b["mw"], b["price"], stamps[n]) for n, b in field.items()], eligible)
    events.append(
        {
            "minute": max(minute, end),
            "type": "end",
            "l1": final.l1,
            "band_ceiling": final.band_ceiling,
            "awards": [
                {"bidder": a.bidder, "tariff": a.tariff, "mw": a.awarded_mw, "zone": a.zone} for a in final.awards
            ],
        }
    )
    return events
