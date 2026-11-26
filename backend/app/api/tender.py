"""The tender in plain words: short sections from verified facts, and what each unusual clause means."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from sqlalchemy import select

from ..agents import tender_path
from ..core.tender_extract import unusual_clauses
from ..core.tender_plain import explain, plain_summary
from ..db import SessionLocal
from ..models import Document
from .deps import latest_tender_facts

router = APIRouter(prefix="/api/tender", tags=["tender"])

_unusual_by_hash: dict[str, list[dict]] = {}


def _unusual() -> list[dict]:
    with SessionLocal() as s:
        sha = s.scalars(select(Document.sha256).where(Document.kind == "tender").limit(1)).first()
    if sha is None:
        return []
    if sha not in _unusual_by_hash:
        path = tender_path()
        _unusual_by_hash[sha] = (
            [{**asdict(f), "meaning": explain(asdict(f))} for f in unusual_clauses(path)] if path else []
        )
    return _unusual_by_hash[sha]


@router.get("/plain")
def plain():
    facts = latest_tender_facts()
    return {"sections": plain_summary(facts), "unusual": _unusual(), "facts": len(facts)}
