from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select

from ..core.excel_engine import WorkbookEngine, get_engine
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


def latest_run(kind: str, document_id: uuid.UUID | None = None) -> dict | None:
    """The most recent finished run of this kind, as a plain dict, or None."""
    with SessionLocal() as session:
        q = select(Run).where(Run.kind == kind, Run.status == "succeeded")
        if document_id is not None:
            q = q.where(Run.document_id == document_id)
        run = session.scalars(q.order_by(Run.finished_at.desc()).limit(1)).first()
        return {"id": run.id, "result": run.result or {}, "finished_at": run.finished_at} if run else None


def latest_tender_facts() -> list[dict]:
    """Facts from the most recent finished Reader run on a tender document, or none."""
    with SessionLocal() as session:
        tender = session.scalars(select(Document.id).where(Document.kind == "tender").limit(1)).first()
        if tender is None:
            return []
        run = session.scalars(
            select(Run)
            .where(Run.kind == "reader", Run.document_id == tender, Run.status == "succeeded")
            .order_by(Run.finished_at.desc())
            .limit(1)
        ).first()
        return list((run.result or {}).get("facts", [])) if run else []
