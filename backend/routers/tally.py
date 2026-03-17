"""Tally ERP router — push transactions to Tally and check connectivity."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter

from backend.models.tally import DEFAULT_TALLY_URL, TallyConfig, TallyPushRequest, TallyPushResponse, TallyVoucherResult
from backend.models.transaction import StatementData, Transaction
from backend.services.tally_service import TallyService

logger = logging.getLogger(__name__)
router = APIRouter()


def _make_response(result: TallyVoucherResult) -> TallyPushResponse:
    """Build a TallyPushResponse from a TallyVoucherResult."""
    if result.errors > 0 and result.created == 0 and result.altered == 0:
        return TallyPushResponse(
            status="error",
            message=f"{result.errors} error(s) occurred. No vouchers were created.",
            result=result,
        )
    parts = []
    if result.created:
        parts.append(f"{result.created} voucher(s) created")
    if result.altered:
        parts.append(f"{result.altered} voucher(s) altered")
    if result.errors:
        parts.append(f"{result.errors} error(s)")
    return TallyPushResponse(
        status="success",
        message=", ".join(parts) if parts else "No vouchers processed.",
        result=result,
    )


@router.post("/push-to-tally", response_model=TallyPushResponse)
async def push_to_tally(request: TallyPushRequest) -> TallyPushResponse:
    """Push extracted bank transactions to Tally ERP as voucher entries."""
    service = TallyService(request.config)
    try:
        result = await service.push_statement(request.statement)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in push_to_tally: %s", exc)
        return TallyPushResponse(
            status="error",
            message=f"Internal error: {exc}",
            result=TallyVoucherResult(errors=1, error_details=[str(exc)]),
        )
    return _make_response(result)


@router.post("/tally/test-push", response_model=TallyPushResponse)
async def tally_test_push(
    tally_url: str = DEFAULT_TALLY_URL,
    bank_ledger_name: str = "ICICI Bank",
) -> TallyPushResponse:
    """Push dummy transactions to Tally for testing — no file upload needed."""
    dummy_statement = StatementData(
        account_holder="Test User",
        bank_name="ICICI Bank",
        account_number="XXXX1234",
        transactions=[
            Transaction(date="2026-03-01", description="salary credit March", credit=50000.0),
            Transaction(date="2026-03-03", description="Test payment entry", debit=2500.0),
            Transaction(date="2026-03-10", description="sales receipt", credit=15000.0),
            Transaction(date="2026-03-15", description="salary April advance", credit=99999.0),
            Transaction(date="2026-03-18", description="vendor payment March", debit=3200.0),
        ],
    )
    config = TallyConfig(tally_url=tally_url, bank_ledger_name=bank_ledger_name, default_ledger="Suspense Account")
    service = TallyService(config)
    try:
        result = await service.push_statement(dummy_statement)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in tally_test_push: %s", exc)
        return TallyPushResponse(
            status="error",
            message=f"Internal error: {exc}",
            result=TallyVoucherResult(errors=1, error_details=[str(exc)]),
        )
    return _make_response(result)


@router.get("/tally/health")
async def tally_health(
    tally_url: str = DEFAULT_TALLY_URL,
    tally_port: int = 9000,
) -> dict:
    """Check whether Tally is reachable at the given URL and port."""
    url = tally_url.rstrip('/')
    base_url = f"{url}:{tally_port}" if url in ("http://localhost", "http://127.0.0.1") or url.startswith(("http://192.", "http://10.")) else url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(base_url, headers={"ngrok-skip-browser-warning": "true"})
        return {"status": "reachable", "tally_url": base_url, "http_status": response.status_code}
    except httpx.ConnectError:
        return {"status": "unreachable", "tally_url": base_url, "error": "Connection refused — Tally is not running or the HTTP server is disabled."}
    except httpx.TimeoutException:
        return {"status": "unreachable", "tally_url": base_url, "error": "Connection timed out."}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "tally_url": base_url, "error": str(exc)}
