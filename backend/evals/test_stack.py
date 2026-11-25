"""Black-box checks over HTTP, the way an external eval suite will hit the app."""

from __future__ import annotations

import time

import httpx
import pytest

pytestmark = pytest.mark.stack


@pytest.fixture(scope="module")
def client(api_url):
    with httpx.Client(base_url=api_url, timeout=120) as c:
        yield c


def _wait(client, run_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("succeeded", "failed"):
            return run
        time.sleep(0.5)
    raise AssertionError(f"Run {run_id} did not finish in {timeout}s")


def test_health_and_selftest(client):
    assert client.get("/health").json()["status"] == "ok"
    st = client.get("/api/selftest").json()
    assert st["ok"], st


def test_samples_seeded_and_read(client):
    docs = client.get("/api/documents").json()
    assert {d["filename"] for d in docs} >= {"bid_model.xlsx", "tender.pdf", "auction_history.xlsx"}
    for d in docs:
        runs = client.get("/api/runs", params={"document_id": d["id"], "kind": "reader"}).json()
        assert runs, f"no reader run for {d['filename']}"
        assert _wait(client, runs[0]["id"])["status"] == "succeeded"


def test_upload_unseen_workbook_then_goal_seek(client, wind_workbook):
    path, truth = wind_workbook
    with open(path, "rb") as fh:
        up = client.post("/api/documents", files={"file": ("wind_vertical.xlsx", fh.read())})
    assert up.status_code in (200, 201), up.text
    doc_id = up.json()["document"]["id"]
    gs = client.post(
        f"/api/workbooks/{doc_id}/goal-seek",
        json={"variable": truth["tariff_cell"], "target": truth["equity_irr_cell"], "target_value": 0.12},
    ).json()
    assert gs["converged"] and abs(gs["value"] - truth["breakeven_12pct"]) < 1e-4


def test_async_engine_run(client):
    wb = next(d for d in client.get("/api/documents").json() if d["filename"] == "bid_model.xlsx")
    run = client.post(
        "/api/runs",
        json={"kind": "engine", "document_id": wb["id"], "params": {"start": 2.4, "stop": 2.8, "step": 0.2}},
    ).json()
    done = _wait(client, run["id"])
    assert done["status"] == "succeeded", done["error"]
    assert abs(done["result"]["breakeven_tariff"] - 2.6039) < 5e-4


def test_rejects_bad_input_cleanly(client):
    r = client.post("/api/documents", files={"file": ("notes.txt", b"hello")})
    assert r.status_code == 415
    r = client.post("/api/runs", json={"kind": "nope"})
    assert r.status_code == 400
