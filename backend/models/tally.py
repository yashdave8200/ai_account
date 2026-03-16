"""
Pydantic models for Tally ERP integration.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from backend.models.transaction import StatementData


class TallyConfig(BaseModel):
    """Configuration for connecting to a Tally ERP instance."""

    tally_url: str = Field("https://jordy-unalienable-renda.ngrok-free.dev", description="Tally HTTP server base URL")
    tally_port: int = Field(9000, description="Tally HTTP server port")
    bank_ledger_name: str = Field(..., description="Name of the bank ledger in Tally")
    default_ledger: str = Field("Suspense Account", description="Default counterpart ledger when description does not map to a known ledger")
    company_name: Optional[str] = Field(None, description="Tally company name (optional; uses currently active company if omitted)")


class TallyVoucherResult(BaseModel):
    """Aggregated result returned by Tally after importing vouchers."""

    created: int = Field(0, description="Number of vouchers created")
    altered: int = Field(0, description="Number of vouchers altered")
    errors: int = Field(0, description="Number of errors encountered")
    error_details: List[str] = Field(default_factory=list, description="List of error messages from Tally")


class TallyPushRequest(BaseModel):
    """Request body for the push-to-tally endpoint."""

    statement: StatementData
    config: TallyConfig


class TallyPushResponse(BaseModel):
    """Response returned after pushing transactions to Tally."""

    status: str = Field(..., description="'success' or 'error'")
    message: str = Field(..., description="Human-readable summary")
    result: Optional[TallyVoucherResult] = Field(None, description="Detailed import result")
