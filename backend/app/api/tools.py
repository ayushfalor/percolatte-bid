"""Synchronous, deterministic tools. Same functions the agents and the chat use.

These are the easiest entry points for an external eval suite: no queue, no
LLM, plain JSON in and out.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException

from ..core import auction_rules as rules
from ..core.excel_engine import EngineError
from ..core.workbook_reader import read_structure
from ..files import materialize
from ..schemas import AllocateIn, EvaluateIn, EvaluateOut, GoalSeekIn, GoalSeekOut, ShortlistIn
from .deps import load_document, workbook_engine

router = APIRouter(prefix="/api", tags=["tools"])


@router.get("/workbooks/{document_id}/structure")
def structure(document_id: uuid.UUID):
    doc = load_document(document_id)
    if doc.kind not in ("workbook", "history"):
        raise HTTPException(400, f"Document is a {doc.kind}, not a workbook")
    ext = "." + doc.filename.rsplit(".", 1)[-1].lower()
    return read_structure(materialize(doc.sha256, ext, doc.content))


@router.post("/workbooks/{document_id}/evaluate", response_model=EvaluateOut)
def evaluate(document_id: uuid.UUID, body: EvaluateIn):
    eng = workbook_engine(document_id)
    t0 = time.perf_counter()
    try:
        values = eng.evaluate(body.overrides, body.outputs)
    except EngineError as exc:
        raise HTTPException(422, str(exc)) from exc
    return EvaluateOut(values=values, elapsed_ms=int((time.perf_counter() - t0) * 1000))


@router.post("/workbooks/{document_id}/goal-seek", response_model=GoalSeekOut)
def goal_seek(document_id: uuid.UUID, body: GoalSeekIn):
    eng = workbook_engine(document_id)
    try:
        r = eng.goal_seek(
            body.variable, body.target, body.target_value, body.lower, body.upper, overrides=body.overrides
        )
    except EngineError as exc:
        raise HTTPException(422, str(exc)) from exc
    return GoalSeekOut(**r.__dict__)


@router.get("/workbooks/{document_id}/parity")
def parity(document_id: uuid.UUID):
    return workbook_engine(document_id).parity().as_dict()


@router.post("/auction/shortlist")
def shortlist(body: ShortlistIn):
    bids = [rules.Bid(**b.model_dump()) for b in body.bids]
    return rules.shortlist_for_era(bids, body.tendered_mw).as_dict()


@router.post("/auction/allocate")
def allocate(body: AllocateIn):
    bids = [rules.Bid(**b.model_dump()) for b in body.bids]
    return rules.allocate(bids, body.eligible_mw).as_dict()
