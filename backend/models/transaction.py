"""
Pydantic models for bank statement transaction data.
Defines the schema for structured output returned by the OCR pipeline.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class Transaction(BaseModel):
    """Represents a single bank transaction."""

    date: Optional[str] = Field(None, description="Transaction date in YYYY-MM-DD format")
    description: str = Field(..., description="Transaction narration or description")
    debit: Optional[float] = Field(None, description="Debit amount (money out)")
    credit: Optional[float] = Field(None, description="Credit amount (money in)")
    balance: Optional[float] = Field(None, description="Running account balance after transaction")
    counterpart_ledger: Optional[str] = Field(
        None,
        description="Human-reviewed counterpart ledger name; overrides auto-detection in Tally push"
    )


class StatementData(BaseModel):
    """Structured representation of a complete bank statement."""

    account_holder: Optional[str] = Field(None, description="Name of the account holder")
    bank_name: Optional[str] = Field(None, description="Name of the bank")
    account_number: Optional[str] = Field(None, description="Masked or full account number")
    transactions: List[Transaction] = Field(default_factory=list, description="List of extracted transactions")


class UploadResponse(BaseModel):
    """Response returned after a successful statement upload and OCR processing."""

    status: str = Field(..., description="Processing status: success or error")
    message: str = Field(..., description="Human-readable result message")
    filename: str = Field(..., description="Original uploaded filename")
    statement: Optional[StatementData] = Field(None, description="Extracted statement data")
    raw_ocr_text: Optional[str] = Field(None, description="Raw OCR output before structuring")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    service: str = "bank-statement-extractor"
