from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Document, Run, Scenario
from ..schemas import RunOut, ScenarioIn, ScenarioOut

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


@router.post("/{scenario_id}/run", response_model=RunOut, status_code=202)
def run_scenario(scenario_id: uuid.UUID):
    """Queue the Engine on this scenario's overrides. The War Room shows the result as a ghost line."""
    with SessionLocal() as s:
        sc = s.get(Scenario, scenario_id)
        if sc is None:
            raise HTTPException(404, "Scenario not found")
        run = Run(
            kind="engine", document_id=sc.document_id, params={"overrides": sc.overrides, "scenario_id": str(sc.id)}
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        return run
