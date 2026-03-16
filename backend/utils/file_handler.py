"""
File handling utilities for bank statement uploads.

Handles:
- Saving uploaded files to a temp directory
- Converting PDF pages to images for OCR processing
- Cleaning up temporary files after processing
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Temp directory for uploaded files (relative to project root)
TEMP_DIR = Path(__file__).parent.parent / "temp_uploads"
TEMP_DIR.mkdir(exist_ok=True)

# Supported MIME types
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
}

# Supported file extensions
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def is_allowed_file(filename: str) -> bool:
    """Check if the uploaded file extension is supported."""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def save_temp_file(content: bytes, original_filename: str) -> Path:
    """
    Save uploaded bytes to a uniquely-named temp file.

    Args:
        content: Raw file bytes from the upload.
        original_filename: Original filename to preserve the extension.

    Returns:
        Path to the saved temp file.
    """
    ext = Path(original_filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = TEMP_DIR / unique_name
    dest.write_bytes(content)
    logger.info("Saved temp file: %s (%d bytes)", dest, len(content))
    return dest


def pdf_to_images(pdf_path: Path) -> List[Path]:
    """
    Convert each page of a PDF into a PNG image.

    Uses pdf2image (poppler) under the hood.
    Each page becomes a separate image saved in TEMP_DIR.

    Args:
        pdf_path: Path to the uploaded PDF file.

    Returns:
        List of Paths to the generated page images, in page order.
    """
    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image is not installed. Run: pip install pdf2image"
        ) from exc

    logger.info("Converting PDF to images: %s", pdf_path)
    pages = convert_from_path(str(pdf_path), dpi=200)

    image_paths: List[Path] = []
    for idx, page in enumerate(pages):
        img_path = TEMP_DIR / f"{pdf_path.stem}_page_{idx + 1}.png"
        page.save(str(img_path), "PNG")
        image_paths.append(img_path)
        logger.debug("Saved page %d → %s", idx + 1, img_path)

    logger.info("PDF converted to %d image(s)", len(image_paths))
    return image_paths


def cleanup_files(*paths: Path) -> None:
    """
    Delete temporary files from disk.

    Silently ignores missing files to avoid errors during cleanup.
    """
    for path in paths:
        try:
            if path.exists():
                path.unlink()
                logger.debug("Deleted temp file: %s", path)
        except OSError as exc:
            logger.warning("Could not delete temp file %s: %s", path, exc)


def get_file_extension(filename: str) -> str:
    """Return the lowercased file extension including the dot."""
    return Path(filename).suffix.lower()
