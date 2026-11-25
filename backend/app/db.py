"""Database engine and session. Tables are created on startup (no migration tool).

Schema changes during development: run `make reset` (drops the Docker volume).
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(retries: int = 60, delay: float = 1.0) -> None:
    """Wait for Postgres, then create tables. Safe to call from api and worker at once."""
    from . import models  # noqa: F401  (registers the tables on Base.metadata)

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT pg_advisory_xact_lock(724001)"))  # one creator at a time
                Base.metadata.create_all(conn)
            return
        except OperationalError as exc:
            last_error = exc
            if attempt == 0:
                log.info("Waiting for the database...")
            time.sleep(delay)
    raise RuntimeError(f"Database not reachable after {retries} tries: {last_error}")
