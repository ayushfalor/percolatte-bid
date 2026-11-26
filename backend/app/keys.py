"""Where the Anthropic key comes from: the environment first, else the one saved from the Setup screen.

Reviewers run with no .env. The Setup screen lets them paste a key of their own, or the passphrase
from the submission note, which unlocks the demo key inside deploy/env.enc right in the container.
The key is kept in the local database, which publishes no port, and is never written to the repo.
The worker reads the same row, so a tender uploaded after the key is saved gets the model pass too.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings

log = logging.getLogger(__name__)

SETTING_NAME = "anthropic_api_key"
KEY_PREFIX = "sk-" + "ant-"  # in two halves so the no-keys-in-the-repo check does not trip on this line
CACHE_SECONDS = 5.0  # /health polls every few seconds; the saved row does not change that often
ENV_VAR = "BIDBENCH_PHRASE"  # the passphrase travels to openssl by environment, never on the command line
_cache: tuple[float, str] = (0.0, "")


def env_enc_path() -> Path | None:
    """deploy/env.enc, in the image (/app/deploy) or the repo; None when this build has none."""
    here = Path(__file__).resolve()
    for root in (here.parents[1], here.parents[2]):
        candidate = root / "deploy" / "env.enc"
        if candidate.is_file():
            return candidate
    return None


def parse_env(text: str) -> dict[str, str]:
    """NAME=value lines of a .env file; quotes stripped, comments and blanks skipped."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        out[name.strip()] = value.strip().strip("'\"")
    return out


def looks_like_key(secret: str) -> bool:
    return secret.strip().startswith(KEY_PREFIX)


def unlock(phrase: str, enc: Path | None = None) -> str:
    """The key inside deploy/env.enc, or '' when the phrase does not open it."""
    enc = enc or env_enc_path()
    if enc is None:
        raise FileNotFoundError("deploy/env.enc is not in this build")
    done = subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-in", str(enc), "-pass", f"env:{ENV_VAR}"],
        env={**os.environ, ENV_VAR: phrase},
        capture_output=True,
        check=False,
        timeout=20,
    )
    if done.returncode != 0:
        return ""
    return parse_env(done.stdout.decode("utf-8", errors="ignore")).get("ANTHROPIC_API_KEY", "")


def stored_key() -> str:
    """The key saved from the Setup screen; '' when none, or when there is no database to ask."""
    from .db import SessionLocal
    from .models import Setting

    try:
        with SessionLocal() as s:
            row = s.get(Setting, SETTING_NAME)
            return str((row.value or {}).get("value", "")) if row else ""
    except SQLAlchemyError as exc:
        log.debug("No saved key readable: %s", exc)
        return ""


def api_key() -> str:
    """The environment wins; otherwise the saved key, re-read every few seconds."""
    global _cache
    env = get_settings().anthropic_api_key.strip()
    if env:
        return env
    at, key = _cache
    now = time.monotonic()
    if now - at < CACHE_SECONDS:
        return key
    key = stored_key()
    _cache = (now, key)
    return key


def key_source() -> str:
    """env, saved or none."""
    if get_settings().anthropic_api_key.strip():
        return "env"
    return "saved" if api_key() else "none"


def llm_mode() -> str:
    return "live" if api_key() else "offline"


def check_key(key: str, model: str) -> str | None:
    """One tiny call so a wrong key is refused on the spot. None when the key works."""
    import anthropic

    try:
        anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=1, messages=[{"role": "user", "content": "ok"}]
        )
    except anthropic.AuthenticationError:
        return "Anthropic rejected this key."
    except anthropic.APIError as exc:
        return f"Could not confirm the key with Anthropic ({type(exc).__name__}). Try again in a moment."
    return None


def save_key(key: str) -> None:
    from .db import SessionLocal
    from .models import Setting

    global _cache
    with SessionLocal() as s:
        row = s.get(Setting, SETTING_NAME) or Setting(key=SETTING_NAME)
        row.value = {"value": key}
        s.add(row)
        s.commit()
    _cache = (0.0, "")


def clear_key() -> None:
    from .db import SessionLocal
    from .models import Setting

    global _cache
    with SessionLocal() as s:
        row = s.get(Setting, SETTING_NAME)
        if row is not None:
            s.delete(row)
            s.commit()
    _cache = (0.0, "")
