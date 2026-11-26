"""Request and response shapes. These are the API contract external evals rely on."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    filename: str
    sha256: str
    size_bytes: int
    meta: dict[str, Any]
    created_at: datetime


class RunCreate(BaseModel):
    kind: str = Field(description="Agent to run: reader, auditor, scout, rival, engine, copilot")
    document_id: uuid.UUID | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    status: str
    document_id: uuid.UUID | None
    params: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    progress: float
    message: str | None
    cost_usd: float
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class UploadOut(BaseModel):
    document: DocumentOut
    created: bool
    reader_run_id: uuid.UUID | None


class ScenarioIn(BaseModel):
    name: str
    document_id: uuid.UUID
    overrides: dict[str, Any] = Field(default_factory=dict)
    rival_run_id: uuid.UUID | None = None
    source: str = "ui"


class ScenarioOut(ScenarioIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime


class EvaluateIn(BaseModel):
    outputs: list[str] = Field(examples=[["Returns!C8", "Returns!C10"]])
    overrides: dict[str, Any] = Field(default_factory=dict, examples=[{"Tariff": 2.5}])


class EvaluateOut(BaseModel):
    values: dict[str, Any]
    elapsed_ms: int


class GoalSeekIn(BaseModel):
    variable: str = Field(examples=["Tariff"])
    target: str = Field(examples=["Returns!C8"])
    target_value: float = Field(examples=[0.14])
    lower: float | None = None
    upper: float | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class GoalSeekOut(BaseModel):
    value: float | None
    achieved: float | None
    iterations: int
    converged: bool
    elapsed_ms: int
    message: str = ""


class BidIn(BaseModel):
    bidder: str
    capacity_mw: float
    tariff: float
    timestamp: float = 0.0
    first_round_tariff: float | None = None


class ShortlistIn(BaseModel):
    tendered_mw: float = 700
    bids: list[BidIn]


class AllocateIn(BaseModel):
    eligible_mw: float = Field(examples=[700])
    bids: list[BidIn]


class ChatIn(BaseModel):
    message: str = Field(examples=["What if the interest rate rises by 50 basis points?"])
    document_id: uuid.UUID | None = Field(default=None, description="The bid model; the seeded one when omitted")
    scenario_id: uuid.UUID | None = Field(default=None, description="Ask about a saved scenario instead of the base")


class ChatOut(BaseModel):
    answer: str
    scenario_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None  # the engine rerun the answer's numbers come from
    grounded: list[str] = Field(default_factory=list)  # every number in the answer, with the tool it came from
    ungrounded: list[str] = Field(default_factory=list)  # always empty for an answer the API lets through
    cost_usd: float = 0.0


class BriefOut(BaseModel):
    document_id: uuid.UUID
    as_received: float | None
    corrected: float | None
    entry_bid: float | None
    target_low: float | None
    target_high: float | None
    walk_away: float | None
    reasons: list[str] = Field(default_factory=list)  # the Engine's own words for the three numbers
    bridge: list[dict[str, Any]]
    depends_most_on: list[dict[str, Any]]
    must_dos: dict[str, Any]
    snapshot_id: str | None
    sources: dict[str, Any]  # which run each block came from, so every number is one click from its origin
    pending: list[str]  # agent runs that have not finished yet, so the UI can say what is still coming
