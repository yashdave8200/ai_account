"""FastAPI router for the rule-based transaction classifier."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from backend.models.classifier import ClassifyBatchRequest, ClassifyBatchResponse
from backend.services.classifier_service import classify_transaction

router = APIRouter()


@router.post("/classify-transactions", response_model=ClassifyBatchResponse)
async def classify_transactions(request: ClassifyBatchRequest) -> ClassifyBatchResponse:
    """Classify a batch of transactions using the rule-based engine."""
    results = await asyncio.gather(
        *[classify_transaction(tx.narration, tx.amount) for tx in request.transactions]
    )
    return ClassifyBatchResponse(total=len(results), classified=list(results))
