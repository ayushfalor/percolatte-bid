"""Health, agent list and a one-call self test (handy for reviewers and CI)."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from .. import __version__
from ..agents import REGISTRY
from ..config import get_settings
from ..core import auction_rules as rules
from ..core.excel_engine import get_engine
from ..db import SessionLocal, engine
from ..files import materialize
from ..models import Document, Run

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    settings = get_settings()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        with SessionLocal() as s:
            counts = dict(s.execute(select(Run.status, func.count()).group_by(Run.status)).all())
        return {"status": "ok", "version": __version__, "database": "ok", "llm_mode": settings.llm_mode, "runs": counts}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "error", "database": str(exc)})


@router.get("/api/agents")
def agents():
    return [{"kind": a.kind, "title": a.title, "job": a.job, "built": a.built} for a in REGISTRY.values()]


@router.get("/api/selftest")
def selftest():
    """End-to-end check without any API key: DB, formula engine on the sample model, auction rules."""
    checks: list[dict] = []

    def check(name: str, fn):
        t0 = time.perf_counter()
        try:
            detail = fn()
            checks.append({"check": name, "ok": True, "detail": detail, "ms": int((time.perf_counter() - t0) * 1000)})
        except Exception as exc:
            checks.append(
                {
                    "check": name,
                    "ok": False,
                    "detail": f"{type(exc).__name__}: {exc}",
                    "ms": int((time.perf_counter() - t0) * 1000),
                }
            )

    def db_check():
        with SessionLocal() as s:
            return {"documents": s.scalar(select(func.count()).select_from(Document))}

    def model_check():
        with SessionLocal() as s:
            doc = s.scalars(select(Document).where(Document.filename == "bid_model.xlsx")).first()
            if doc is None:
                raise RuntimeError("Sample bid_model.xlsx not seeded")
            path = materialize(doc.sha256, ".xlsx", doc.content)
        eng = get_engine(path)
        irr = eng.evaluate({}, ["Returns!C8"])["Returns!C8"]
        seek = eng.goal_seek("Tariff", "Returns!C8", 0.14)
        assert abs(irr - 0.142107489734805) < 1e-9, irr
        assert seek.converged and abs(seek.value - 2.6039) < 5e-4, seek
        return {"equity_irr_at_2_62": round(irr, 6), "breakeven_tariff_14pct": round(seek.value, 4)}

    def rules_check():
        bids = [
            rules.Bid("L1", 50, 1.65),
            rules.Bid("L2", 150, 1.66),
            rules.Bid("L3a", 200, 1.68, 1),
            rules.Bid("L3b", 300, 1.68, 2),
            rules.Bid("L3c", 50, 1.68, 3),
            rules.Bid("L4", 200, 1.70),
            rules.Bid("L5", 100, 1.71),
        ]
        alloc = rules.allocate(bids, 700)
        winners = [a.bidder for a in alloc.awards if a.awarded_mw > 0]
        assert winners == ["L1", "L2", "L3a", "L3b"], winners
        return {"rfs_41_3_winners": winners, "band_ceiling": alloc.band_ceiling}

    check("database", db_check)
    check("formula engine on sample model", model_check)
    check("auction rules vs RfS 41.3 example", rules_check)
    ok = all(c["ok"] for c in checks)
    return JSONResponse(status_code=200 if ok else 500, content={"ok": ok, "checks": checks})
