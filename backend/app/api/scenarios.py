from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Document, Scenario
from ..schemas import ScenarioIn, ScenarioOut

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@router.post("", response_model=ScenarioOut, status_code=201)
def create_scenario(body: ScenarioIn):
    with SessionLocal() as s:
        if s.get(Document, body.document_id) is None:
            raise HTTPException(404, "Document not found")
        sc = Scenario(**body.model_dump())
        s.add(sc)
        s.commit()
        s.refresh(sc)
        return sc


@router.get("", response_model=list[ScenarioOut])
def list_scenarios():
    with SessionLocal() as s:
        return list(s.scalars(select(Scenario).order_by(Scenario.created_at.desc())))
