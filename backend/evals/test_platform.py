"""Platform guarantees that every later phase relies on."""
from __future__ import annotations


def test_runs_are_write_once_over_the_api():
    """No route can edit or delete a run, so a finished rival snapshot can never change."""
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/runs"):
            assert not ({"PUT", "PATCH", "DELETE"} & set(getattr(route, "methods", set()))), path


def test_contracts_are_importable():
    from app.core import audit, contracts, rival_model, simulate, tender_extract  # noqa: F401

    assert {"history", "almm_40", "almm_100"} == set(rival_model.REGIMES)
