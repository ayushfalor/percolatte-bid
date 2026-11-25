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
    return created
