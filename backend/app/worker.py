"""Background worker: claims queued runs from Postgres and executes the agent.

Queue = the runs table. `FOR UPDATE SKIP LOCKED` lets you run several workers
safely (docker compose up --scale worker=3). No Redis needed.
"""

from __future__ import annotations

import logging
import signal
import time
import traceback
from datetime import UTC, datetime

from sqlalchemy import text, update

from .agents import REGISTRY, NotBuiltYet, make_context
from .config import get_settings
from .db import SessionLocal, engine, init_db
from .models import Run

log = logging.getLogger("worker")

CLAIM = text(
    """
    UPDATE runs SET status = 'running', started_at = now(), progress = 0
    WHERE id = (
        SELECT id FROM runs WHERE status = 'queued'
        ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
    )
    RETURNING id
    """
)

_stop = False


def _handle_stop(*_: object) -> None:
    global _stop
    _stop = True


def claim_one():
    with engine.begin() as conn:
        row = conn.execute(CLAIM).first()
        return row[0] if row else None


def execute(run_id) -> str:
    """Run one job to completion. Returns the final status."""
    with SessionLocal() as s:
        run = s.get(Run, run_id)
        spec = REGISTRY.get(run.kind)
        ctx = make_context(run)
    status, result, error = "succeeded", None, None
    started = time.perf_counter()
    try:
        if spec is None:
            raise ValueError(f"Unknown agent '{run.kind}'")
        result = spec.fn(ctx)
        result = {**(result or {}), "elapsed_ms": int((time.perf_counter() - started) * 1000)}
    except NotBuiltYet as exc:
        status, error = "failed", str(exc)
    except Exception as exc:  # the run records the failure; the worker keeps going
        status, error = "failed", f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=6)}"
        log.exception("Run %s (%s) failed", run_id, run.kind)
    with engine.begin() as conn:
        conn.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "running")
            .values(
                status=status,
                result=result,
                error=error,
                progress=1.0 if status == "succeeded" else Run.progress,
                finished_at=datetime.now(UTC),
            )
        )
    return status


def recover_stale() -> None:
    """A worker that died mid-run leaves rows in 'running'. Fail them loudly instead of hanging."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE runs SET status='failed', error='Worker restarted while this run was in progress', "
                "finished_at=now() WHERE status='running' AND started_at < now() - interval '15 minutes'"
            )
        )


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    init_db()
    recover_stale()
    log.info("Worker ready, agents: %s", ", ".join(REGISTRY))
    while not _stop:
        run_id = claim_one()
        if run_id is None:
            time.sleep(settings.worker_poll_seconds)
            continue
        log.info("Running %s", run_id)
        log.info("Run %s finished: %s", run_id, execute(run_id))
    log.info("Worker stopped")


if __name__ == "__main__":
    main()
