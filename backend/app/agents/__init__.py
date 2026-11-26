"""Agent registry. One module per agent, one function per agent: run(ctx) -> dict.

Agents never write to the database themselves; the worker stores whatever
they return as the run's result. That keeps every agent easy to test
(call it with a fake context) and keeps finished runs immutable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update

from ..config import Settings, get_settings
from ..db import SessionLocal
from ..db import engine as db_engine
from ..files import materialize
from ..models import Document, Run


class NotBuiltYet(RuntimeError):
    """Raised by agents that are still stubs in the scaffold."""


@dataclass
class AgentContext:
    run_id: Any
    kind: str
    params: dict[str, Any]
    document_id: Any | None
    settings: Settings

    def progress(self, fraction: float, message: str | None = None) -> None:
        """Visible live in the UI while the run is still going (separate short transaction)."""
        with db_engine.begin() as conn:
            conn.execute(
                update(Run).where(Run.id == self.run_id).values(progress=max(0.0, min(1.0, fraction)), message=message)
            )

    def document(self) -> tuple[Document, str]:
        """The run's document plus a local file path for it."""
        if self.document_id is None:
            raise ValueError(f"The {self.kind} agent needs a document_id")
        with SessionLocal() as s:
            doc = s.get(Document, self.document_id)
            if doc is None:
                raise ValueError(f"Document {self.document_id} not found")
            ext = "." + doc.filename.rsplit(".", 1)[-1].lower()
            path = materialize(doc.sha256, ext, doc.content)
            return doc, path

    def latest_result(self, kind: str, document_id: Any | None = None) -> dict[str, Any] | None:
        """Read another agent's latest finished output (agents never call each other directly)."""
        with SessionLocal() as s:
            q = select(Run).where(Run.kind == kind, Run.status == "succeeded")
            if document_id is not None:
                q = q.where(Run.document_id == document_id)
            run = s.scalars(q.order_by(Run.finished_at.desc()).limit(1)).first()
            return run.result if run else None


AgentFn = Callable[[AgentContext], dict[str, Any]]


@dataclass(frozen=True)
class AgentSpec:
    kind: str
    title: str
    job: str
    built: bool
    fn: AgentFn


REGISTRY: dict[str, AgentSpec] = {}


def agent(kind: str, title: str, job: str, built: bool = True) -> Callable[[AgentFn], AgentFn]:
    def wrap(fn: AgentFn) -> AgentFn:
        REGISTRY[kind] = AgentSpec(kind, title, job, built, fn)
        return fn

    return wrap


def make_context(run: Run) -> AgentContext:
    return AgentContext(run.id, run.kind, run.params or {}, run.document_id, get_settings())


def tender_document_id() -> Any | None:
    """The tender in the workspace, if one has been uploaded. Read-only."""
    with SessionLocal() as s:
        return s.scalars(select(Document.id).where(Document.kind == "tender").limit(1)).first()


# Import order = pipeline order, and REGISTRY keeps it, so do not let isort sort this line.
from . import reader, auditor, scout, rival, modeling, copilot  # noqa: E402,F401,I001
