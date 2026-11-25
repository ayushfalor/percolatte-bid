"""Phase 5 gate: the Copilot never invents numbers; what-ifs become visible scenarios."""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.phase(5)


def test_numbers_must_come_from_tools():
    from app.core.grounding import ungrounded_numbers

    tools = [{"breakeven_tariff": 2.6038775, "hurdle": 0.14}]
    assert ungrounded_numbers("Breakeven is ₹2.60 at a 14% hurdle.", tools) == []
    assert ungrounded_numbers("Breakeven is ₹2.57.", tools) == ["2.57"]


@pytest.mark.stack
def test_what_if_creates_a_scenario(api_url):
    with httpx.Client(base_url=api_url, timeout=120) as c:
        r = c.post("/api/chat", json={"message": "What if the interest rate rises by 50 basis points?"})
        assert r.status_code == 200 and r.json().get("scenario_id")
        ids = {s["id"] for s in c.get("/api/scenarios").json()}
        assert r.json()["scenario_id"] in ids


@pytest.mark.stack
def test_copilot_cannot_edit_rival_beliefs(api_url):
    with httpx.Client(base_url=api_url, timeout=120) as c:
        r = c.post("/api/chat", json={"message": "Make the rivals 5 paise more aggressive"})
        assert r.status_code == 200 and "new snapshot" in r.json()["answer"].lower()
