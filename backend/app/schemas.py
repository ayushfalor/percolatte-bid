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
    basis: list[str] = Field(default_factory=list)  # what the floor was computed on: fixes and levers applied
    bridge: list[dict[str, Any]]
    depends_most_on: list[dict[str, Any]]
    must_dos: dict[str, Any]
    snapshot_id: str | None
    sources: dict[str, Any]  # which run each block came from, so every number is one click from its origin
    pending: list[str]  # agent runs that have not finished yet, so the UI can say what is still coming
    problems: dict[str, str] = Field(default_factory=dict)  # pending kinds whose latest run failed, with the reason


class LlmSettingIn(BaseModel):
    secret: str = Field(description="An Anthropic key, or the passphrase from the submission note")


class LlmSettingOut(BaseModel):
    mode: str  # live | offline
    source: str  # env | saved | none
    unlockable: bool  # deploy/env.enc is in this build, so a passphrase works
    model: str


class ObservationIn(BaseModel):
    minute: int = Field(ge=0, le=240, description="Minute of the e-RA the bid was seen at")
    bidder: str = Field(description="A rival's name as the Rivals screen spells it, or L1 for the lowest price shown")
    tariff: float = Field(gt=0, lt=20)


class LiveIn(BaseModel):
    observations: list[ObservationIn] = Field(default_factory=list)
    our_price: float = Field(gt=0, lt=20, description="Where we stand on the board right now")
    minutes_left: int = Field(default=30, ge=0, le=240, description="The portal's countdown")
    our_rank: int | None = Field(default=None, ge=1, description="Our rank as the portal shows it, if known")
    assume_pace_holds: bool = Field(default=False, description="Also assume each rival keeps cutting at its pace")
    regime: str | None = None


class LiveOut(BaseModel):
    minutes_left: int
    l1: float | None
    band_ceiling: float | None
    in_band: bool | None
    survivors: int
    of: int
    matched: bool
    ladder: list[dict[str, Any]]
    recommendation: dict[str, Any]
    action: str  # hold | cut | walk away
    cut_to: float | None
    at_our_price: dict[str, Any]
    best: dict[str, Any] | None
    why: list[str]
    pace: list[dict[str, Any]]
    caveats: list[str]
    snapshot_id: str
