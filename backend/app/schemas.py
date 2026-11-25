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
