"""The Copilot over HTTP, and the Bid Brief assembled from stored runs.

Both read finished agent runs and tender facts. Neither computes a bid number of its own: the
Brief hands back what the Auditor, Rival model and Engine stored, each block naming its run, and
the chat path goes through the Copilot agent, whose answers are checked by core.grounding.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from ..agents import copilot
from ..core.brief import bridge_steps, must_dos
from ..core.contracts import Finding, Fix
from ..core.simulate import replay
from ..db import SessionLocal
from ..files import materialize
from ..models import Document, Run, Scenario
from ..schemas import BriefOut, ChatIn, ChatOut
from .deps import latest_failure, latest_run, latest_snapshot, latest_tender_facts, workbook_document

router = APIRouter(prefix="/api", tags=["copilot"])
TOP_DRIVERS = 3


def _path(doc: Document) -> str:
    ext = "." + doc.filename.rsplit(".", 1)[-1].lower()
    return materialize(doc.sha256, ext, doc.content)


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    """Ask a question or a what-if. A what-if becomes a scenario and an engine rerun."""
    doc = workbook_document(body.document_id)
    path = _path(doc)
    stored = copilot.Stored(
        (latest_run("engine", doc.id) or {}).get("result"),
        (latest_run("auditor", doc.id) or {}).get("result"),
        latest_tender_facts(),
    )
    reply = copilot.answer(body.message, path, stored)

    scenario_id = run_id = None
    with SessionLocal() as s:
        if reply["scenario"]:
            scenario = Scenario(
                name=reply["scenario"]["name"][:200],
                document_id=doc.id,
                overrides=reply["scenario"]["overrides"],
                source="chat",
            )
            s.add(scenario)
            s.flush()
            rerun = Run(
                kind="engine",
                document_id=doc.id,
                params={"overrides": reply["scenario"]["overrides"], "scenario_id": str(scenario.id)},
            )
            s.add(rerun)
            s.flush()
            scenario_id, run_id = scenario.id, rerun.id
        log = Run(
            kind="copilot",
            status="succeeded",
            document_id=doc.id,
            params={"message": body.message},
            result={k: v for k, v in reply.items() if k != "scenario"},
            progress=1.0,
            cost_usd=reply["cost_usd"],
        )
        s.add(log)
        s.commit()
    return ChatOut(
        answer=reply["answer"],
        scenario_id=scenario_id,
        run_id=run_id,
        grounded=reply["grounded"],
        ungrounded=reply["ungrounded"],
        cost_usd=reply["cost_usd"],
    )


@router.get("/replay/{document_id}")
def replay_auction(
    document_id: uuid.UUID, draw: int = 0, open: float = 2.45, floor: float = 2.28, regime: str = "almm_40"
):
    """One simulated e-RA, minute by minute, from the latest rival snapshot. For the war room."""
    doc = workbook_document(document_id)
    snapshot = latest_snapshot(regime)
    if snapshot is None:
        raise HTTPException(409, "No rival run yet; run the Rival model first")
    our_mw = float(((latest_run("engine", doc.id) or {}).get("result") or {}).get("our_mw", 200))
    return {"snapshot_id": snapshot.id, "draw": draw, "events": replay(snapshot, draw, open, floor, our_mw)}


def _finding(row: dict[str, Any]) -> Finding:
    fix = row.get("fix")
    return Finding(
        **{
            **row,
            "fix": Fix(**fix) if fix else None,
            "assumptions": tuple(row.get("assumptions", ())),
            "clauses": tuple(row.get("clauses", ())),
        }
    )


@router.get("/brief/{document_id}", response_model=BriefOut)
def brief(document_id: uuid.UUID):
    """The Bid Brief: three numbers, the bridge, what it depends on, the must-dos. Stored runs only."""
    doc = workbook_document(document_id)
    auditor = latest_run("auditor", doc.id)
    engine = latest_run("engine", doc.id)
    rival = latest_run("rival")
    facts = latest_tender_facts()
    pending = [kind for kind, run in (("auditor", auditor), ("rival", rival), ("engine", engine)) if run is None]
    problems = {
        kind: why for kind in pending if (why := latest_failure(kind, None if kind == "rival" else doc.id)) is not None
    }

    audit = (auditor or {}).get("result") or {}
    findings = [_finding(f) for f in audit.get("findings", [])]
    as_received, corrected = audit.get("breakeven_as_received"), audit.get("corrected_breakeven")
    rec = ((engine or {}).get("result") or {}).get("recommendation") or {}
    return BriefOut(
        document_id=doc.id,
        as_received=as_received,
        corrected=corrected,
        entry_bid=rec.get("entry_bid"),
        target_low=rec.get("target_low"),
        target_high=rec.get("target_high"),
        walk_away=rec.get("walk_away"),
        reasons=list(rec.get("reasons", [])),
        basis=list(((engine or {}).get("result") or {}).get("basis", [])),
        bridge=bridge_steps(findings, as_received, corrected) if findings and as_received and corrected else [],
        depends_most_on=(audit.get("drivers") or [])[:TOP_DRIVERS],
        must_dos=must_dos(facts),
        snapshot_id=((engine or {}).get("result") or {}).get("snapshot_id"),
        sources={
            kind: str(run["id"]) for kind, run in (("auditor", auditor), ("rival", rival), ("engine", engine)) if run
        },
        pending=pending,
        problems=problems,
    )
