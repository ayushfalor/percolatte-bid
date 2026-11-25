from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..agents import REGISTRY
from ..db import SessionLocal
from ..models import Document, Run
from ..schemas import RunCreate, RunOut

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunOut, status_code=202)
def create_run(body: RunCreate):
    """Queue an agent run. Poll GET /api/runs/{id} for progress and result."""
    if body.kind not in REGISTRY:
        raise HTTPException(400, f"Unknown agent '{body.kind}'. Known: {', '.join(REGISTRY)}")
    with SessionLocal() as s:
        if body.document_id and s.get(Document, body.document_id) is None:
            raise HTTPException(404, "Document not found")
        run = Run(kind=body.kind, document_id=body.document_id, params=body.params)
        s.add(run)
        s.commit()
        s.refresh(run)
        return run


@router.get("", response_model=list[RunOut])
def list_runs(
    kind: str | None = None,
    status: str | None = None,
    document_id: uuid.UUID | None = None,
    limit: int = 50,
):
    with SessionLocal() as s:
        q = select(Run).order_by(Run.created_at.desc()).limit(min(limit, 500))
        if kind:
            q = q.where(Run.kind == kind)
        if status:
            q = q.where(Run.status == status)
        if document_id:
            q = q.where(Run.document_id == document_id)
        return list(s.scalars(q))


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID):
    with SessionLocal() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run
