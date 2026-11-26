from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from sqlalchemy import select

from ..config import get_settings
from ..core.template import check_bid_model
from ..db import SessionLocal
from ..files import detect_kind, materialize, sha256
from ..models import Document
from ..schemas import DocumentOut, UploadOut
from ..seed import add_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(kind: str | None = None):
    with SessionLocal() as s:
        q = select(Document).order_by(Document.created_at)
        if kind:
            q = q.where(Document.kind == kind)
        return list(s.scalars(q))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID):
    with SessionLocal() as s:
        doc = s.get(Document, document_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        return doc


@router.post("", response_model=UploadOut, status_code=201)
async def upload(response: Response, file: UploadFile = File(...)):
    """Upload a bid model (.xlsx/.xlsm), a tender (.pdf) or auction history (.xlsx). Queues the Reader."""
    content = await file.read()
    limit = get_settings().max_upload_mb * 1024 * 1024
    if len(content) > limit:
        raise HTTPException(413, f"File is larger than {get_settings().max_upload_mb} MB")
    if not content:
        raise HTTPException(400, "Empty file")
    name = file.filename or "upload"
    try:
        kind = detect_kind(name, content)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    if kind == "workbook":
        ext = "." + name.rsplit(".", 1)[-1].lower()
        check = check_bid_model(materialize(sha256(content), ext, content))
        if not check.ok:
            raise HTTPException(422, {"message": check.message, "missing": check.missing, "template": "/api/template"})
    doc, created, run = add_document(name, content)
    if not created:
        response.status_code = 200  # same file already stored (deduplicated by hash)
    return UploadOut(document=DocumentOut.model_validate(doc), created=created, reader_run_id=run.id if run else None)
