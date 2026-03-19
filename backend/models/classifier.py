"""Pydantic v2 models for the transaction classifier."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel


class ClassifyRequest(BaseModel):
    narration: str
    amount: float


class ClassifyBatchRequest(BaseModel):
    transactions: List[ClassifyRequest]


class ClassificationResult(BaseModel):
    narration: str
    amount: float
    ledger_name: str
    group: str
    reason: str
    confidence: Literal["high", "medium", "low"]
    validation_status: Literal["valid", "flagged"]
    validation_notes: List[str]


class ClassifyBatchResponse(BaseModel):
    total: int
    classified: List[ClassificationResult]
