"""The live auction: type in the board as it moves, get the next move back. Nothing is stored."""

from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from ..core.live_auction import Observation, live_read
from ..schemas import LiveIn, LiveOut
from .deps import latest_run, latest_snapshot, workbook_document

router = APIRouter(prefix="/api", tags=["live"])


@router.post("/live/{document_id}", response_model=LiveOut)
def live(document_id: uuid.UUID, body: LiveIn):
    """Conditional ladder and advice from the latest Engine run, the rival snapshot and the bids typed in."""
    doc = workbook_document(document_id)
    engine = (latest_run("engine", doc.id) or {}).get("result") or {}
    if not engine.get("curve") or engine.get("breakeven_tariff") is None:
        raise HTTPException(409, "No Engine run for this model yet; start one from Setup")
    regime = body.regime or str(engine.get("regime") or "almm_40")
    snapshot = latest_snapshot(regime)
    if snapshot is None:
        raise HTTPException(409, "No rival run yet; run the Rival model first")
    read = live_read(
        snapshot,
        engine["curve"],
        hurdle_tariff=float(engine["breakeven_tariff"]),
        dscr_tariff=engine.get("dscr_tariff"),
        observations=[Observation(**o.model_dump()) for o in body.observations],
        our_price=body.our_price,
        minutes_left=body.minutes_left,
        our_rank=body.our_rank,
        assume_pace_holds=body.assume_pace_holds,
        our_mw=float(engine.get("our_mw", 200)),
    )
    return LiveOut(
        minutes_left=read.minutes_left,
        l1=read.l1,
        band_ceiling=read.band_ceiling,
        in_band=read.in_band,
        survivors=read.survivors,
        of=read.of,
        matched=read.matched,
        ladder=[asdict(p) for p in read.ladder],
        recommendation=asdict(read.recommendation),
        action=read.action,
        cut_to=read.cut_to,
        at_our_price=asdict(read.at_our_price),
        best=asdict(read.best) if read.best else None,
        why=read.why,
        pace=[asdict(p) for p in read.pace],
        caveats=read.caveats,
        snapshot_id=read.snapshot_id,
    )
