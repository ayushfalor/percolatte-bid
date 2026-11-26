"""The template: what a bid model needs, and the sample model to download and copy."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import get_settings
from ..core.template import requirements

router = APIRouter(prefix="/api/template", tags=["template"])
TEMPLATE_FILE = "bid_model.xlsx"


@router.get("/requirements")
def template_requirements():
    """What the app looks for in a bid model, in the words the Setup screen shows."""
    return {"requirements": requirements(), "download": "/api/template"}


@router.get("")
def download_template():
    """The sample bid model as a file to copy: every label the app needs, laid out the usual way."""
    path = Path(get_settings().samples_dir) / TEMPLATE_FILE
    if not path.is_file():
        raise HTTPException(404, "The sample model is not in this build")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="bid_model_template.xlsx",
    )
