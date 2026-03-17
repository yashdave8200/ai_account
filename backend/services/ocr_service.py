"""OCR Service — uses OpenAI GPT-4o mini vision API to extract bank statement data."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from openai import AsyncOpenAI

from backend.models.transaction import StatementData, Transaction

logger = logging.getLogger(__name__)

# Cached OpenAI client (initialised once)
_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client


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


async def _ocr_image_with_gpt(image_path: Path) -> str:
    """Send a single image to GPT-4o mini and return the text response."""
    logger.info("Sending image to GPT-4o mini: %s", image_path)
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")

    response = await _get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}", "detail": "high"}},
                {"type": "text", "text": _EXTRACTION_PROMPT},
            ],
        }],
        max_tokens=4096,
    )
    text = response.choices[0].message.content or ""
    logger.debug("GPT-4o mini output (%d chars): %.300s…", len(text), text)
    return text


async def extract_statement(image_paths: List[Path]) -> tuple[str, StatementData]:
    """Run OCR on all pages, parse each page individually, then merge transactions."""
    page_texts: List[str] = []
    all_transactions: List[Transaction] = []
    meta: Optional[StatementData] = None

    for img_path in image_paths:
        try:
            text = await _ocr_image_with_gpt(img_path)
            page_texts.append(text)
            page_statement = _parse_ocr_text(text)
            all_transactions.extend(page_statement.transactions)
            # Take account meta from the first page that has it
            if meta is None or (not meta.account_holder and page_statement.account_holder):
                meta = page_statement
        except Exception as exc:
            logger.error("OCR failed for %s: %s", img_path, exc)
            page_texts.append("")

    raw_text = "\n\n".join(page_texts)
    logger.info("Total OCR text: %d characters across %d page(s)", len(raw_text), len(image_paths))

    statement = StatementData(
        account_holder=meta.account_holder if meta else None,
        bank_name=meta.bank_name if meta else None,
        account_number=meta.account_number if meta else None,
        transactions=all_transactions,
    )
    return raw_text, statement


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_ocr_text(text: str) -> StatementData:
    """Try JSON parse first; fall back to plain-text regex extraction."""
    statement = _try_parse_json(text)
    if statement:
        logger.info("Parsed statement from JSON output")
        return statement
    logger.info("JSON parse failed — falling back to plain-text extraction")
    return _parse_plain_text(text)


def _try_parse_json(text: str) -> Optional[StatementData]:
    """Try to extract a JSON object from the OCR text."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{[\s\S]+\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        txs = [
            Transaction(
                date=tx.get("date"),
                description=tx.get("description") or "—",
                debit=_to_float(tx.get("debit")),
                credit=_to_float(tx.get("credit")),
                balance=_to_float(tx.get("balance")),
            )
            for tx in data.get("transactions", [])
        ]
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
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_plain_text(text: str) -> StatementData:
    """Fallback: extract header fields and transaction rows via regex."""
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
    return StatementData(
        account_holder=account_holder,
        bank_name=bank_name,
        account_number=account_number,
        transactions=_extract_transactions(text),
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
        if re.search(r"date|description|narration|debit|credit|balance|withdrawal|deposit", line, re.IGNORECASE):
            continue
        tx = _cells_to_transaction(re.split(r"\s{2,}|\t", line))
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
        debit, credit, balance = numeric_values[0] or None, numeric_values[1] or None, numeric_values[2]
    elif len(numeric_values) == 2:
        debit, balance = numeric_values[0] or None, numeric_values[1]
    elif len(numeric_values) == 1:
        balance = numeric_values[0]

    return Transaction(date=date_str, description=description or "—", debit=debit, credit=credit, balance=balance)


_DATE_PATTERNS = [
    (r"^(\d{4}-\d{2}-\d{2})$",       "%Y-%m-%d"),
    (r"^(\d{2}/\d{2}/\d{4})$",       "%d/%m/%Y"),
    (r"^(\d{2}-\d{2}-\d{4})$",       "%d-%m-%Y"),
    (r"^(\d{2}/\d{2}/\d{2})$",       "%d/%m/%y"),
    (r"^(\d{1,2}\s+\w{3}\s+\d{4})$", "%d %b %Y"),
    (r"^(\d{2}\.\d{2}\.\d{4})$",     "%d.%m.%Y"),
]


def _try_parse_date(value: str) -> Optional[str]:
    value = value.strip()
    for pattern, fmt in _DATE_PATTERNS:
        m = re.match(pattern, value)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None
