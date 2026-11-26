from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import HTTPException
from sqlalchemy import select

from ..core.contracts import RivalProfile, RivalSnapshot
from ..core.excel_engine import WorkbookEngine, get_engine
from ..core.tender_extract import extract_facts
from ..db import SessionLocal
from ..files import materialize
from ..models import Document, Run


def load_document(document_id: uuid.UUID) -> Document:
    with SessionLocal() as s:
        doc = s.get(Document, document_id)
        if doc is None:
            raise HTTPException(404, f"Document {document_id} not found")
        _ = doc.content  # load the deferred column while the session is open
        return doc


def workbook_engine(document_id: uuid.UUID) -> WorkbookEngine:
    doc = load_document(document_id)
    if doc.kind not in ("workbook", "history"):
        raise HTTPException(400, f"Document {document_id} is a {doc.kind}, not a workbook")
    ext = "." + doc.filename.rsplit(".", 1)[-1].lower()
    return get_engine(materialize(doc.sha256, ext, doc.content))


def latest_run(kind: str, document_id: uuid.UUID | None = None, base_only: bool = True) -> dict | None:
    """The most recent finished run of this kind, as a plain dict, or None.

    A what-if reruns the engine with overrides. Those runs belong to their scenario; the Brief
    and the War Room's base line must come from a run without overrides, so by default they
    are skipped.
    """
    with SessionLocal() as session:
        q = select(Run).where(Run.kind == kind, Run.status == "succeeded")
        if document_id is not None:
            q = q.where(Run.document_id == document_id)
        for run in session.scalars(q.order_by(Run.finished_at.desc()).limit(50)):
            params = run.params or {}
            if base_only and ("scenario_id" in params or params.get("overrides")):
                continue
            return {"id": run.id, "result": run.result or {}, "finished_at": run.finished_at}
        return None


_facts_by_hash: dict[str, list[dict]] = {}


def latest_tender_facts() -> list[dict]:
    """Facts from the most recent finished Reader run on a tender document.

    When that run predates extraction, or has not finished, the facts are read from the tender
    file itself: the rule pass needs no key and takes about a second, and the result is kept per
    file hash so polling screens do not reopen the PDF.
    """
    with SessionLocal() as session:
        tender = session.scalars(select(Document).where(Document.kind == "tender").limit(1)).first()
        if tender is None:
            return []
        run = session.scalars(
            select(Run)
            .where(Run.kind == "reader", Run.document_id == tender.id, Run.status == "succeeded")
            .order_by(Run.finished_at.desc())
            .limit(1)
        ).first()
        facts = list((run.result or {}).get("facts", [])) if run else []
        if facts:
            return facts
        if tender.sha256 not in _facts_by_hash:
            ext = "." + tender.filename.rsplit(".", 1)[-1].lower()
            path = materialize(tender.sha256, ext, tender.content)
            _facts_by_hash[tender.sha256] = [asdict(f) for f in extract_facts(path)]
        return _facts_by_hash[tender.sha256]


def workbook_document(document_id: uuid.UUID | None) -> Document:
    """The bid model to work on: the one asked for, or the first one uploaded."""
    if document_id is not None:
        doc = load_document(document_id)
        if doc.kind != "workbook":
            raise HTTPException(400, f"Document {document_id} is a {doc.kind}, not a bid model")
        return doc
    with SessionLocal() as s:
        doc = s.scalars(select(Document).where(Document.kind == "workbook").order_by(Document.created_at)).first()
        if doc is None:
            raise HTTPException(404, "No bid model uploaded yet")
        _ = doc.content
        return doc


def latest_snapshot(regime: str) -> RivalSnapshot | None:
    """The frozen rival beliefs for one regime, from the latest finished Rival run."""
    stored = (((latest_run("rival") or {}).get("result") or {}).get("snapshots") or {}).get(regime)
    if not stored:
        return None
    return RivalSnapshot(**{**stored, "profiles": [RivalProfile(**p) for p in stored["profiles"]]})
