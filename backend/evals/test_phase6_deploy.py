"""Phase 6 gate: deployed, backed up, secrets out of the repo, and the README finished."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import httpx
import pytest

pytestmark = pytest.mark.phase(6)

REPO = "ayushfalor/percolatte-bid"
SECTIONS = {
    # heading: (minimum words, phrases that must appear)
    "## What we built and why, what we left out, where it breaks": (150, ["Where it breaks", "left out"]),
    "## LLM cost": (60, ["offline", "cost_usd", "tender"]),
    "## How this becomes a product a renewable developer would pay for": (150, ["INR", "pilot"]),
}


def _section(readme: str, heading: str) -> str:
    start = readme.find(heading)
    assert start >= 0, f"missing {heading!r}"
    rest = readme[start + len(heading) :]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


# ---------- the README is finished ----------


def test_readme_has_no_todos(repo_root):
    assert "TODO" not in (repo_root / "README.md").read_text()


def test_readme_has_no_placeholders(repo_root):
    readme = (repo_root / "README.md").read_text()
    assert "YOUR_GITHUB_USER" not in readme
    assert REPO in readme, "the badge and clone command must point at the real repository"


@pytest.mark.parametrize("heading", list(SECTIONS))
def test_readme_sections_have_substance(repo_root, heading):
    """A section that exists but says nothing would pass the no-TODO check. It must say something."""
    body = _section((repo_root / "README.md").read_text(), heading)
    minimum, phrases = SECTIONS[heading]
    assert len(body.split()) >= minimum, f"{heading}: {len(body.split())} words"
    for phrase in phrases:
        assert phrase.lower() in body.lower(), f"{heading} must mention {phrase!r}"


def test_where_it_breaks_lists_real_limits(repo_root):
    body = _section(
        (repo_root / "README.md").read_text(), "## What we built and why, what we left out, where it breaks"
    )
    bullets = [line for line in body.splitlines() if line.startswith("- ")]
    assert len(bullets) >= 4, "at least four stated limits"


def test_llm_cost_section_is_honest(repo_root):
    """Only tender extraction can call a model. The README must not imply more, and must say offline is free."""
    body = _section((repo_root / "README.md").read_text(), "## LLM cost").lower()
    assert "offline" in body and ("zero" in body or "0" in body)
    assert "extraction" in body or "tender" in body


# ---------- secrets stay on the host ----------


def _tracked_files(repo_root) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=repo_root, capture_output=True, text=True)
    except FileNotFoundError:  # no git binary inside the image
        out = subprocess.CompletedProcess(args=[], returncode=1, stdout="")
    if out.returncode != 0:  # inside the image there is no .git; the file list is what was copied in
        found = (p for p in repo_root.rglob("*") if p.is_file() and ".venv" not in p.parts)
        return [str(p.relative_to(repo_root)) for p in found]
    return out.stdout.split()


KEY_PREFIX = "sk-" + "ant-"  # built in two halves so this file does not trip its own check


def test_secrets_never_in_the_repo(repo_root):
    files = _tracked_files(repo_root)
    assert ".env" not in files, ".env must stay ignored"
    for name in files:
        path = repo_root / name
        if path.suffix in (".png", ".xlsx", ".pdf", ".drawio", ".gz", ".pyc") or not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        assert KEY_PREFIX not in text, f"an API key is written into {name}"


def test_production_compose_references_secrets_by_name(repo_root):
    prod = (repo_root / "docker-compose.prod.yml").read_text()
    for line in prod.splitlines():
        if line.strip().startswith("#"):
            continue  # a comment naming the variable is not a value
        if "ANTHROPIC_API_KEY" in line or "POSTGRES_PASSWORD" in line:
            assert "${" in line, f"a secret is written literally: {line.strip()}"


# ---------- backup and restore ----------


def test_database_backup_script_exists(repo_root):
    assert (repo_root / "scripts" / "backup-db.sh").is_file()
    assert (repo_root / "scripts" / "restore-db.sh").is_file()


@pytest.mark.stack
def test_backup_and_restore_round_trip(repo_root, tmp_path, api_url):
    """A dump of the live database restores into a scratch database with the same documents."""
    script = str(repo_root / "scripts" / "backup-db.sh")
    dump = subprocess.run(["bash", script, str(tmp_path)], capture_output=True, text=True)
    assert dump.returncode == 0, dump.stderr
    files = list(tmp_path.glob("*.sql.gz"))
    assert files and files[0].stat().st_size > 1000, "an empty dump is not a backup"

    restore = subprocess.run(
        ["bash", str(repo_root / "scripts" / "restore-db.sh"), str(files[0]), "bidbench_restore_check"],
        capture_output=True,
        text=True,
    )
    assert restore.returncode == 0, restore.stderr
    assert re.search(r"documents:\s*(\d+)", restore.stdout), restore.stdout
    restored = int(re.search(r"documents:\s*(\d+)", restore.stdout).group(1))
    with httpx.Client(base_url=api_url, timeout=60) as c:
        live = len(c.get("/api/documents").json())
    assert restored == live


# ---------- production configuration and CD ----------


def test_production_compose_validates(repo_root):
    """The production override composes with the base file into a valid stack."""
    if shutil.which("docker") is None:
        pytest.skip("docker is not on PATH here")
    out = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml", "config", "--quiet"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={**os.environ, "DOMAIN": "example.com", "POSTGRES_PASSWORD": "x"},
    )
    assert out.returncode == 0, out.stderr
    prod = (repo_root / "docker-compose.prod.yml").read_text()
    assert "caddy" in prod.lower(), "HTTPS termination is part of production"
    assert "backup" in prod, "a nightly backup service is part of production"


def test_deploy_workflow_runs_on_tags_and_smokes(repo_root):
    text = (repo_root / ".github" / "workflows" / "deploy.yml").read_text()
    assert "tags:" in text and re.search(r"['\"]v\*['\"]", text), "deploy on a v* tag"
    assert "DEPLOY_URL" in text and "smoke.sh" in text, "the live smoke test runs after the deploy"
    assert "secrets." in text, "the host and key come from GitHub secrets, never the file"


def test_deployed_app_is_healthy():
    url = os.environ.get("DEPLOY_URL")
    if not url:
        pytest.skip("DEPLOY_URL not set")
    with httpx.Client(base_url=url.rstrip("/"), timeout=60) as c:
        assert c.get("/health").json()["status"] == "ok"
        assert c.get("/api/selftest").json()["ok"]
        assert '<div id="root">' in c.get("/").text, "the UI is served at the root"
        docs = c.get("/api/documents").json()
        assert any(d["filename"] == "bid_model.xlsx" for d in docs)
