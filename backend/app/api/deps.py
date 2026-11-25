from __future__ import annotations

import uuid

from fastapi import HTTPException

from ..core.excel_engine import WorkbookEngine, get_engine
from ..db import SessionLocal
from ..files import materialize
from ..models import Document


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
