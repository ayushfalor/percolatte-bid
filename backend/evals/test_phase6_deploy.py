"""Phase 6 gate: deployed, backed up, and the README is finished."""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.phase(6)


def test_readme_has_no_todos(repo_root):
    assert "TODO" not in (repo_root / "README.md").read_text()


def test_database_backup_script_exists(repo_root):
    assert (repo_root / "scripts" / "backup-db.sh").is_file()


def test_deployed_app_is_healthy():
    url = os.environ.get("DEPLOY_URL")
    if not url:
        pytest.skip("DEPLOY_URL not set")
    with httpx.Client(base_url=url.rstrip("/"), timeout=60) as c:
        assert c.get("/health").json()["status"] == "ok"
        assert c.get("/api/selftest").json()["ok"]
