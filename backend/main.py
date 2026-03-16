"""
Bank Statement Extractor — FastAPI application entry point.

Wires up:
- CORS middleware (permissive for local dev)
- Statement router under /api prefix
- Structured logging
- Lifespan events for startup / shutdown hooks
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.statement import router as statement_router
from backend.routers.tally import router as tally_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("backend.services.tally_service").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown hooks."""
    logger.info("Bank Statement Extractor starting up…")
    yield
    logger.info("Bank Statement Extractor shutting down…")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Bank Statement Extractor",
    description=(
        "Upload bank statements (PDF / JPG / PNG) and extract structured "
        "transaction data via the GLM-OCR HuggingFace Space."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins for local development; restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(statement_router, prefix="/api", tags=["Statements"])
app.include_router(tally_router, prefix="/api", tags=["Tally"])
