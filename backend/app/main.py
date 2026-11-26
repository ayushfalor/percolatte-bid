"""FastAPI app. Interactive API docs at /docs."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import chat, documents, live, runs, scenarios, system, tender, tools
from .api import settings as llm_settings
from .config import get_settings
from .db import init_db
from .seed import seed_samples

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.seed_samples:
        seed_samples()
    yield


app = FastAPI(title="Bid Workbench API", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for module in (system, documents, runs, scenarios, tools, chat, live, tender, llm_settings):
    app.include_router(module.router)
