"""
OCR Service — uses the MinerU2.5 model via HuggingFace transformers pipeline.

Workflow:
  1. Accept one or more image file paths (PDF pages are pre-converted upstream).
  2. Load the `opendatalab/MinerU2.5-2509-1.2B` image-text-to-text pipeline once
     and cache it for the lifetime of the process.
  3. Send each image with an extraction prompt asking for structured JSON output.
  4. Aggregate text across all pages.
  5. Parse the structured text into a StatementData object.

Model:
  opendatalab/MinerU2.5-2509-1.2B
  Pipeline type: image-text-to-text
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from PIL import Image

from backend.models.transaction import StatementData, Transaction

logger = logging.getLogger(__name__)

# Model identifier
MODEL_ID = "opendatalab/MinerU2.5-2509-1.2B"

# Cached pipeline (loaded once on first use)
_pipeline = None
_pipeline_loaded = False  # True once we've attempted a load (success or fail)


def _get_pipeline():
    """
    Lazily load and cache the MinerU transformers pipeline.
    Loading is expensive; it is done only once and the result is cached.
    Raises RuntimeError on load failure (does not retry infinitely).
    """
    global _pipeline, _pipeline_loaded

    if _pipeline_loaded:
        if _pipeline is None:
            raise RuntimeError("MinerU pipeline failed to load on startup.")
        return _pipeline

    logger.info("Loading MinerU pipeline (%s) — this may take a moment…", MODEL_ID)
    try:
        from transformers import pipeline  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "transformers is not installed. Run: pip install transformers"
        ) from exc

    try:
        _pipeline = pipeline(
            "image-text-to-text",
            model=MODEL_ID,
        )
        logger.info("MinerU pipeline loaded successfully.")
    finally:
        _pipeline_loaded = True  # mark as attempted even if it failed

    return _pipeline


# Extraction prompt sent with every page image
_EXTRACTION_PROMPT = (
    "You are a financial document parser. "
    "Extract ALL content from this bank statement image. "
    "Return a single JSON object with this exact structure:\n"
    '{\n'
    '  "account_holder": "<name or null>",\n'
    '  "bank_name": "<bank name or null>",\n'
    '  "account_number": "<account number or null>",\n'
    '  "transactions": [\n'
    '    {\n'
    '      "date": "YYYY-MM-DD or null",\n'
    '      "description": "<narration>",\n'
    '      "debit": <number or null>,\n'
    '      "credit": <number or null>,\n'
    '      "balance": <number or null>\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "Include every transaction row. Output only the JSON, no markdown fences."
)


async def run_ocr_on_image(image_path: Path) -> str:
    """
    Run MinerU on a single image and return the model's text output.

    The pipeline call is synchronous; it is executed in a thread pool
    to avoid blocking the FastAPI event loop.

    Args:
        image_path: Local path to the image file.

    Returns:
        Raw text/JSON string from the model.
    """
    logger.info("Running MinerU OCR on: %s", image_path)

    def _call_sync() -> str:
        pipe = _get_pipeline()

        # Open image as PIL object so we don't depend on URL accessibility
        image = Image.open(str(image_path)).convert("RGB")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text",  "text": _EXTRACTION_PROMPT},
                ],
            }
        ]

        result = pipe(text=messages, max_new_tokens=4096)

        # transformers returns a list of dicts; extract the generated text
        if isinstance(result, list) and result:
            output = result[0]
            # Common keys: 'generated_text' (str or list)
            generated = output.get("generated_text", "")
            if isinstance(generated, list):
                # Chat format: list of messages; last assistant turn
                for msg in reversed(generated):
                    if isinstance(msg, dict) and msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            # content blocks
                            return " ".join(
                                c.get("text", "") for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                            )
                        return str(content)
                # Fallback: last item text
                last = generated[-1]
                return str(last.get("content", last)) if isinstance(last, dict) else str(last)
            return str(generated)

        return str(result)

    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _call_sync)
    logger.debug("MinerU output (%d chars): %.300s…", len(text), text)
    return text


async def extract_statement(
    image_paths: List[Path],
) -> tuple[str, StatementData]:
    """
    Run OCR on all pages and parse the combined output into StatementData.

    Args:
        image_paths: Ordered list of image paths (one per PDF page, or a single image).

    Returns:
        Tuple of (raw_ocr_text, StatementData).
    """
    page_texts: List[str] = []

    for img_path in image_paths:
        try:
            text = await run_ocr_on_image(img_path)
            page_texts.append(text)
        except Exception as exc:
            logger.error("OCR failed for %s: %s", img_path, exc)
            page_texts.append("")

    raw_text = "\n\n".join(page_texts)
    logger.info(
        "Total OCR text: %d characters across %d page(s)",
        len(raw_text), len(image_paths),
    )

    statement = _parse_ocr_text(raw_text)
    return raw_text, statement


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_ocr_text(text: str) -> StatementData:
    """
    Convert raw MinerU output into a StatementData object.

    Strategy:
      1. Try to parse JSON directly (model usually returns structured JSON).
      2. Fall back to regex + line-by-line extraction.
    """
    statement = _try_parse_json(text)
    if statement:
        logger.info("Parsed statement from JSON output")
        return statement

    logger.info("JSON parse failed — falling back to plain-text extraction")
    return _parse_plain_text(text)


def _try_parse_json(text: str) -> Optional[StatementData]:
    """Try to extract a JSON object from the OCR text."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()

    match = re.search(r"\{[\s\S]+\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        # Normalise transactions list
        txs = []
        for tx in data.get("transactions", []):
            txs.append(Transaction(
                date=tx.get("date"),
                description=tx.get("description") or "—",
                debit=_to_float(tx.get("debit")),
                credit=_to_float(tx.get("credit")),
                balance=_to_float(tx.get("balance")),
            ))
        return StatementData(
            account_holder=data.get("account_holder"),
            bank_name=data.get("bank_name"),
            account_number=data.get("account_number"),
            transactions=txs,
        )
    except Exception as exc:
        logger.debug("JSON parse error: %s", exc)
        return None


def _to_float(value) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_plain_text(text: str) -> StatementData:
    """
    Fallback: extract header fields and transaction rows via regex.
    Used only when the model does not return valid JSON.
    """
    account_holder = _extract_field(text, [
        r"(?:account\s*holder|name)[:\s]+([A-Za-z\s]+?)(?:\n|$)",
        r"(?:customer\s*name)[:\s]+([A-Za-z\s]+?)(?:\n|$)",
    ])
    bank_name = _extract_field(text, [
        r"(?:bank\s*name|bank)[:\s]+([A-Za-z\s&]+?)(?:\n|$)",
        r"^([A-Za-z\s]+Bank[A-Za-z\s]*)$",
    ])
    account_number = _extract_field(text, [
        r"(?:account\s*(?:no|number|#))[:\s]+([0-9X*\-]+)",
        r"(?:a/?c\s*(?:no|number)?)[:\s]+([0-9X*\-]+)",
    ])

    transactions = _extract_transactions(text)

    return StatementData(
        account_holder=account_holder,
        bank_name=bank_name,
        account_number=account_number,
        transactions=transactions,
    )


def _extract_field(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def _extract_transactions(text: str) -> List[Transaction]:
    transactions: List[Transaction] = []

    # Strategy A: Markdown pipe tables
    pipe_rows = re.findall(r"\|([^|\n]+\|[^|\n]+\|[^|\n]+)", text)
    if pipe_rows:
        for row in pipe_rows:
            cells = [c.strip() for c in row.split("|") if c.strip()]
            if len(cells) < 3:
                continue
            tx = _cells_to_transaction(cells)
            if tx:
                transactions.append(tx)
        if transactions:
            return transactions

    # Strategy B: Whitespace/tab-separated lines
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.search(r"date|description|narration|debit|credit|balance|withdrawal|deposit",
                     line, re.IGNORECASE):
            continue
        parts = re.split(r"\s{2,}|\t", line)
        tx = _cells_to_transaction(parts)
        if tx:
            transactions.append(tx)

    return transactions


def _cells_to_transaction(cells: List[str]) -> Optional[Transaction]:
    if not cells:
        return None

    date_str: Optional[str] = None
    description_parts: List[str] = []
    numeric_values: List[float] = []

    for cell in cells:
        if date_str is None:
            parsed = _try_parse_date(cell)
            if parsed:
                date_str = parsed
                continue
        val = _to_float(cell)
        if val is not None:
            numeric_values.append(val)
        elif cell:
            description_parts.append(cell)

    description = " ".join(description_parts).strip()
    if not description and not date_str:
        return None

    debit = credit = balance = None
    if len(numeric_values) >= 3:
        debit   = numeric_values[0] or None
        credit  = numeric_values[1] or None
        balance = numeric_values[2]
    elif len(numeric_values) == 2:
        debit   = numeric_values[0] or None
        balance = numeric_values[1]
    elif len(numeric_values) == 1:
        balance = numeric_values[0]

    return Transaction(
        date=date_str,
        description=description or "—",
        debit=debit,
        credit=credit,
        balance=balance,
    )


_DATE_PATTERNS = [
    (r"^(\d{4}-\d{2}-\d{2})$",       "%Y-%m-%d"),
    (r"^(\d{2}/\d{2}/\d{4})$",       "%d/%m/%Y"),
    (r"^(\d{2}-\d{2}-\d{4})$",       "%d-%m-%Y"),
    (r"^(\d{2}/\d{2}/\d{2})$",       "%d/%m/%y"),
    (r"^(\d{1,2}\s+\w{3}\s+\d{4})$", "%d %b %Y"),
    (r"^(\d{2}\.\d{2}\.\d{4})$",     "%d.%m.%Y"),
]


def _try_parse_date(value: str) -> Optional[str]:
    from datetime import datetime
    value = value.strip()
    for pattern, fmt in _DATE_PATTERNS:
        m = re.match(pattern, value)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None
