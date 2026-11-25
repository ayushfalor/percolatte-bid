from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.config import get_settings

EXPECTED = Path(__file__).parent / "expected"


def _repo_root() -> Path | None:
    """Repo root locally (backend/..) or /app in the container: wherever docs/phases/status.json is."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "docs" / "phases" / "status.json").is_file():
            return parent
    return None


def phase_status() -> dict:
    root = _repo_root()
    if root is None:
        return {"completed": 0, "current": 1}
    return json.loads((root / "docs" / "phases" / "status.json").read_text())


def pytest_collection_modifyitems(config, items):
    """Phase gate: tests of unfinished phases are expected to fail; finished phases must pass."""
    done = int(phase_status().get("completed", 0))
    for item in items:
        marker = item.get_closest_marker("phase")
        if marker and int(marker.args[0]) > done:
            item.add_marker(pytest.mark.xfail(reason=f"phase {marker.args[0]} not closed yet", strict=False))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    root = _repo_root()
    if root is None:
        pytest.fail("docs/phases/status.json not found (docs are part of the build)")
    return root


@pytest.fixture(scope="session")
def samples() -> Path:
    path = Path(get_settings().samples_dir)
    assert path.is_dir(), f"Sample files not found at {path}"
    return path


@pytest.fixture(scope="session")
def expected():
    return {p.stem: json.loads(p.read_text()) for p in EXPECTED.glob("*.json")}


@pytest.fixture(scope="session")
def bid_engine(samples):
    from app.core.excel_engine import WorkbookEngine

    return WorkbookEngine(str(samples / "bid_model.xlsx"))


@pytest.fixture(scope="session")
def tender_pages(samples):
    from app.core.tender_reader import read_pages

    return read_pages(str(samples / "tender.pdf"))


@pytest.fixture(scope="session")
def wind_workbook(tmp_path_factory):
    from evals.fixtures.make_workbooks import make_wind_vertical

    path = tmp_path_factory.mktemp("unseen") / "wind_vertical.xlsx"
    truth = make_wind_vertical(str(path))
    return path, truth


@pytest.fixture(scope="session")
def bugged_workbook(tmp_path_factory):
    """The unseen wind model with the sample's two traps planted on a different layout."""
    from evals.fixtures.make_workbooks import make_wind_with_planted_bugs

    path = tmp_path_factory.mktemp("unseen") / "wind_bugged.xlsx"
    truth = make_wind_with_planted_bugs(str(path))
    return path, truth


@pytest.fixture(scope="session")
def whole_column_workbook(tmp_path_factory):
    """A scenario tab read only through VLOOKUP over whole columns."""
    from evals.fixtures.make_workbooks import make_wind_whole_column

    path = tmp_path_factory.mktemp("unseen") / "wind_whole_column.xlsx"
    return path, make_wind_whole_column(str(path))


@pytest.fixture(scope="session")
def idc_workbook(tmp_path_factory):
    """A model whose capex depends on itself through interest during construction."""
    from evals.fixtures.make_workbooks import make_idc_loop

    path = tmp_path_factory.mktemp("unseen") / "idc_loop.xlsx"
    return path, make_idc_loop(str(path))


@pytest.fixture(scope="session")
def api_url() -> str:
    url = os.environ.get("API_URL")
    if not url:
        pytest.skip("API_URL not set (stack tests run in CI and via `make eval`)")
    return url.rstrip("/")


@pytest.fixture(scope="module")
def api_client(api_url):
    """HTTP client for stack tests that live beside their phase's other evals."""
    import httpx

    with httpx.Client(base_url=api_url, timeout=120) as client:
        yield client
