"""Docs are part of the product: a phase is not done until its doc answers reviewers' questions."""
from __future__ import annotations

import json

REQUIRED = ["## Goal", "## What we built", "## How to check it", "## Eval results", "## Questions they may ask"]


def test_phase_plan_and_status(repo_root):
    status = json.loads((repo_root / "docs/phases/status.json").read_text())
    assert 0 <= status["completed"] < status["current"] <= 7
    assert (repo_root / "docs/phases/PLAN.md").is_file()


def test_every_closed_phase_has_a_complete_doc(repo_root):
    status = json.loads((repo_root / "docs/phases/status.json").read_text())
    for n in range(0, status["completed"] + 1):
        doc = repo_root / f"docs/phases/phase-{n}.md"
        assert doc.is_file(), doc
        text = doc.read_text()
        missing = [h for h in REQUIRED if h not in text]
        assert not missing, f"phase-{n}.md missing {missing}"
        assert text.count("**Q:") >= 6, f"phase-{n}.md needs at least 6 reviewer questions with answers"


def test_assumptions_register_and_readme(repo_root):
    assumptions = (repo_root / "ASSUMPTIONS.md").read_text()
    assert sum(1 for line in assumptions.splitlines() if line.startswith("| A-")) >= 10
    readme = (repo_root / "README.md").read_text()
    assert "## Run it" in readme and "docker compose up --build" in readme
