"""Statement router — upload, OCR-process, and retrieve bank statement transactions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.models.transaction import HealthResponse, StatementData, UploadResponse
from backend.services.ocr_service import extract_statement
from backend.utils.file_handler import (
    cleanup_files,
    get_file_extension,
    is_allowed_file,
    pdf_to_images,
    save_temp_file,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory store for the most recently extracted statement.
# For a production system this would be persisted to a database.
# ---------------------------------------------------------------------------
_latest_statement: dict = {}


@router.post(
    "/upload-statement",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload a bank statement and extract transactions via MinerU",
)
async def upload_statement(file: UploadFile = File(...)) -> UploadResponse:
    """Accept a PDF, JPG, or PNG bank statement, OCR it via MinerU, and return structured transactions."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Allowed: PDF, JPG, PNG. Got: {file.filename}",
        )

    logger.info("Received upload: %s (content-type=%s)", file.filename, file.content_type)

    # Read file bytes
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Save to temp
    temp_file = save_temp_file(content, file.filename)
    temp_images = []

    try:
        ext = get_file_extension(file.filename)

        # Convert PDF pages to images; images are used directly
        if ext == ".pdf":
            logger.info("Converting PDF to images for OCR…")
            temp_images = pdf_to_images(temp_file)
        else:
            temp_images = [temp_file]

        if not temp_images:
            raise HTTPException(status_code=422, detail="Could not extract any pages from the file.")

        # Run OCR via MinerU model
        logger.info("Sending %d image(s) to GPT-4o mini…", len(temp_images))
        raw_text, statement = await extract_statement(temp_images)

        # Cache for GET /transactions
        global _latest_statement
        _latest_statement = statement.model_dump()

        logger.info(
            "Extraction complete — %d transactions found for %s",
            len(statement.transactions),
            file.filename,
        )

        return UploadResponse(
            status="success",
            message=f"Extracted {len(statement.transactions)} transaction(s) from {file.filename}.",
            filename=file.filename,
            statement=statement,
            raw_ocr_text=raw_text,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error during statement processing: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"OCR processing failed: {exc}",
        ) from exc
    finally:
        # Always clean up temp files (PDF source + generated page images)
        cleanup_files(temp_file, *temp_images)


@router.get(
    "/transactions",
    response_model=StatementData,
    summary="Return the most recently extracted transaction data",
)
async def get_transactions() -> StatementData:
    """
    Return the structured statement from the most recent /upload-statement call.
    Returns 404 if no statement has been processed yet.
    """
    if not _latest_statement:
        raise HTTPException(
            status_code=404,
            detail="No statement has been processed yet. Upload a statement first.",
        )
    return StatementData(**_latest_statement)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
)
async def health_check() -> HealthResponse:
    """Returns service health status."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        service="bank-statement-extractor",
    )
