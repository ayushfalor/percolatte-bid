"""Turn live AI on from the Setup screen: a key of your own, or the passphrase that unlocks the demo key."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import keys
from ..config import get_settings
from ..schemas import LlmSettingIn, LlmSettingOut

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/llm", response_model=LlmSettingOut)
def llm_setting():
    return LlmSettingOut(
        mode=keys.llm_mode(),
        source=keys.key_source(),
        unlockable=keys.env_enc_path() is not None,
        model=get_settings().llm_model_smart,
    )


@router.post("/llm", response_model=LlmSettingOut)
def set_llm(body: LlmSettingIn):
    """Paste an Anthropic key or the passphrase from the submission note. Checked before it is saved."""
    secret = body.secret.strip()
    if not secret:
        raise HTTPException(400, "Paste the passphrase from the submission note, or an Anthropic key.")
    if keys.looks_like_key(secret):
        key = secret
    else:
        try:
            key = keys.unlock(secret)
        except FileNotFoundError as exc:
            raise HTTPException(409, f"{exc}; paste a key instead.") from exc
        if not key:
            raise HTTPException(
                400, "That passphrase does not unlock the demo key. It is case-sensitive; check for typos."
            )
    problem = keys.check_key(key, get_settings().llm_model_fast)
    if problem:
        raise HTTPException(400, problem)
    keys.save_key(key)
    return llm_setting()


@router.delete("/llm", response_model=LlmSettingOut)
def clear_llm():
    """Forget the saved key. A key set in the environment stays; it is not ours to remove."""
    keys.clear_key()
    return llm_setting()
