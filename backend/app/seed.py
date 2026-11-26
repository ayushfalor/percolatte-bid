"""Load the three sample files on first start, so reviewers land on a ready workspace."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .files import ALLOWED, detect_kind, sha256
from .models import Document, Run

log = logging.getLogger(__name__)


def add_document(filename: str, content: bytes, enqueue_reader: bool = True) -> tuple[Document, bool, Run | None]:
    """Store a file (deduplicated by hash). Returns (document, created, reader_run)."""
    digest = sha256(content)
    with SessionLocal() as s:
        existing = s.scalars(select(Document).where(Document.sha256 == digest)).first()
        if existing:
            return existing, False, None
        kind = detect_kind(filename, content)
        doc = Document(kind=kind, filename=filename, sha256=digest, size_bytes=len(content), content=content, meta={})
        s.add(doc)
        s.flush()
        run = None
        if enqueue_reader:
            run = Run(kind="reader", document_id=doc.id, params={})
            s.add(run)
            # A bid model gets audited and priced by itself; the worker runs jobs in the order queued.
            if kind == "workbook":
                s.add(Run(kind="auditor", document_id=doc.id, params={}))
                s.add(Run(kind="engine", document_id=doc.id, params={}))
        s.commit()
        return doc, True, run


def seed_samples() -> int:
    folder = Path(get_settings().samples_dir)
    if not folder.is_dir():
        log.warning("Samples folder %s not found, skipping seed", folder)
        return 0
    created = 0
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in ALLOWED:
            _, was_created, _ = add_document(path.name, path.read_bytes())
            created += int(was_created)
    if created:
        log.info("Seeded %d sample file(s) from %s", created, folder)
        queue_first_run()
    reread_stale_tenders()
    return created


def queue_first_run() -> None:
    """On a fresh database, run the whole pipeline once so the Brief fills in with no clicks.

    Readers are already queued per file. The rival model needs the history, and the engine needs
    the rival run before it, so the order here is the order the worker will execute them in.
    """
    with SessionLocal() as s:
        history = s.scalars(select(Document).where(Document.kind == "history").limit(1)).first()
        if history is not None:
            s.add(Run(kind="rival", document_id=history.id, params={}))
        for workbook in s.scalars(select(Document).where(Document.kind == "workbook")):
            s.add(Run(kind="engine", document_id=workbook.id, params={"reason": "first start, after the rivals"}))
        s.commit()


def reread_stale_tenders() -> int:
    """Queue a fresh Reader run for a tender whose stored result predates fact extraction.

    A database that outlived an upgrade keeps the old Reader result, which has no facts. Reading
    the tender again heals it; finished runs are never edited, so this is a new row.
    """
    queued = 0
    with SessionLocal() as s:
        for doc in s.scalars(select(Document).where(Document.kind == "tender")):
            latest = s.scalars(
                select(Run)
                .where(Run.kind == "reader", Run.document_id == doc.id)
                .order_by(Run.created_at.desc())
                .limit(1)
            ).first()
            if latest is None or latest.status in ("queued", "running"):
                continue
            if latest.status == "succeeded" and "facts" in (latest.result or {}):
                continue
            s.add(Run(kind="reader", document_id=doc.id, params={"reason": "stored result has no tender facts"}))
            queued += 1
        s.commit()
    if queued:
        log.info("Queued %d fresh Reader run(s) for tenders without facts", queued)
    return queued
