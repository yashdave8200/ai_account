"""TallyService — pushes bank statement transactions to Tally ERP via its HTTP XML API."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

import httpx

from backend.models.tally import TallyConfig, TallyVoucherResult
from backend.models.transaction import StatementData, Transaction

logger = logging.getLogger(__name__)

# Keyword patterns → ledger name for auto-detecting counterpart from transaction description
_LEDGER_KEYWORDS: list[tuple[str, str]] = [
    (r"salary|payroll|sal\b",               "Salary Account"),
    (r"rent\b",                              "Rent Expense"),
    (r"electricity|power\s*bill|bescom|msedcl", "Electricity Charges"),
    (r"internet|broadband|airtel|jio|bsnl", "Internet Charges"),
    (r"insurance|lic\b|premium",            "Insurance Premium"),
    (r"tax|tds|gst\b|income\s*tax",         "Tax Payable"),
    (r"interest\s+received|int\s+cr",       "Interest Received"),
    (r"dividend",                            "Dividend Income"),
    (r"refund",                              "Refund Income"),
]


class TallyService:
    """Sends bank statement transactions to Tally as vouchers via HTTP XML."""

    def __init__(self, config: TallyConfig) -> None:
        self._config = config
        url = config.tally_url.rstrip('/')
        # Don't append port for ngrok/external URLs (they use standard 80/443)
        if url in ("http://localhost", "http://127.0.0.1") or url.startswith(("http://192.", "http://10.")):
            self._base_url = f"{url}:{config.tally_port}"
        else:
            self._base_url = url

    async def push_statement(self, statement: StatementData) -> TallyVoucherResult:
        """Push all transactions in *statement* to Tally as a single batch."""
        voucher_xmls: list[str] = []

        for tx in statement.transactions:
            if tx.debit is None and tx.credit is None:
                logger.warning("Skipping transaction with no debit/credit: %s", tx.description)
                continue
            counterpart = tx.counterpart_ledger or self._guess_counterpart_ledger(tx.description or "", self._config.default_ledger)
            voucher_xmls.append(self._build_voucher_xml(tx, self._config.bank_ledger_name, counterpart))

        if not voucher_xmls:
            return TallyVoucherResult(errors=1, error_details=["No valid transactions found to push."])

        result = await self._post_to_tally(self._build_envelope(voucher_xmls))
        # Tally returns CREATED=1 as a success flag, not a voucher count
        if result.errors == 0 and not result.error_details:
            result.created = len(voucher_xmls)
        return result

    def _build_voucher_xml(self, tx: Transaction, bank_ledger: str, counterpart_ledger: str) -> str:
        """Build a single <VOUCHER> XML string (Receipt for credits, Payment for debits)."""
        is_receipt = tx.credit is not None and (tx.credit or 0) > 0
        voucher_type = "Receipt" if is_receipt else "Payment"
        amount = abs(tx.credit if is_receipt else (tx.debit or 0))
        formatted_date = self._format_date(tx.date)
        narration = (tx.description or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if is_receipt:
            first_ledger, first_positive, first_amount = bank_ledger, "Yes", amount
            second_ledger, second_positive, second_amount = counterpart_ledger, "No", -amount
        else:
            first_ledger, first_positive, first_amount = counterpart_ledger, "Yes", amount
            second_ledger, second_positive, second_amount = bank_ledger, "No", -amount

        return (
            f'<VOUCHER VCHTYPE="{voucher_type}" ACTION="Create">\n'
            f"  <DATE>{formatted_date}</DATE>\n"
            f"  <EFFECTIVEDATE>{formatted_date}</EFFECTIVEDATE>\n"
            f"  <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>\n"
            f"  <NARRATION>{narration}</NARRATION>\n"
            f"  <PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>\n"
            f"  <ISINVOICE>No</ISINVOICE>\n"
            f"  <ALLLEDGERENTRIES.LIST>\n"
            f"    <LEDGERNAME>{first_ledger}</LEDGERNAME>\n"
            f"    <ISDEEMEDPOSITIVE>{first_positive}</ISDEEMEDPOSITIVE>\n"
            f"    <AMOUNT>{first_amount:.2f}</AMOUNT>\n"
            f"  </ALLLEDGERENTRIES.LIST>\n"
            f"  <ALLLEDGERENTRIES.LIST>\n"
            f"    <LEDGERNAME>{second_ledger}</LEDGERNAME>\n"
            f"    <ISDEEMEDPOSITIVE>{second_positive}</ISDEEMEDPOSITIVE>\n"
            f"    <AMOUNT>{second_amount:.2f}</AMOUNT>\n"
            f"  </ALLLEDGERENTRIES.LIST>\n"
            f"</VOUCHER>"
        )

    def _build_envelope(self, voucher_xmls: list[str], from_date: str = "20250401", to_date: str = "20260331") -> str:
        """Wrap vouchers in a Tally import envelope — each voucher in its own <TALLYMESSAGE>."""
        tallymessages = "\n".join(
            f"      <TALLYMESSAGE>\n{xml}\n      </TALLYMESSAGE>"
            for xml in voucher_xmls
        )
        company_tag = ""
        if self._config.company_name:
            name = self._config.company_name.replace("&", "&amp;")
            company_tag = f"\n        <SVCURRENTCOMPANY>{name}</SVCURRENTCOMPANY>"

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<ENVELOPE>\n"
            "  <HEADER>\n"
            "    <VERSION>1</VERSION>\n"
            "    <TALLYREQUEST>Import</TALLYREQUEST>\n"
            "    <TYPE>Data</TYPE>\n"
            "    <ID>Vouchers</ID>\n"
            "  </HEADER>\n"
            "  <BODY>\n"
            f"    <DESC>\n"
            f"      <STATICVARIABLES>{company_tag}\n"
            f"        <SVFROMDATE>{from_date}</SVFROMDATE>\n"
            f"        <SVTODATE>{to_date}</SVTODATE>\n"
            f"      </STATICVARIABLES>\n"
            f"    </DESC>\n"
            "    <DATA>\n"
            f"{tallymessages}\n"
            "    </DATA>\n"
            "  </BODY>\n"
            "</ENVELOPE>"
        )

    async def _post_to_tally(self, xml_body: str) -> TallyVoucherResult:
        """POST the XML envelope to Tally and parse the response."""
        try:
            logger.debug("Sending to Tally:\n%s", xml_body)
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self._base_url,
                    content=xml_body.encode("utf-8"),
                    headers={"Content-Type": "application/xml", "ngrok-skip-browser-warning": "true"},
                )
            response.raise_for_status()
            logger.debug("Tally raw response: %s", response.text)
            return self._parse_response(response.text)

        except httpx.ConnectError:
            msg = f"Tally is not running on {self._base_url}. Please start Tally and enable the HTTP server."
            logger.error(msg)
            return TallyVoucherResult(errors=1, error_details=[msg])
        except httpx.TimeoutException:
            msg = f"Connection to Tally timed out ({self._base_url})."
            logger.error(msg)
            return TallyVoucherResult(errors=1, error_details=[msg])
        except httpx.HTTPStatusError as exc:
            msg = f"Tally returned HTTP {exc.response.status_code}."
            logger.error(msg)
            return TallyVoucherResult(errors=1, error_details=[msg])
        except Exception as exc:  # noqa: BLE001
            msg = f"Unexpected error communicating with Tally: {exc}"
            logger.exception(msg)
            return TallyVoucherResult(errors=1, error_details=[msg])

    def _parse_response(self, xml_text: str) -> TallyVoucherResult:
        """Parse Tally's XML import response."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("Could not parse Tally response XML: %s | raw: %.300s", exc, xml_text)
            if "ok" in xml_text.lower() or "success" in xml_text.lower():
                return TallyVoucherResult(created=1)
            return TallyVoucherResult(errors=1, error_details=[f"Unparseable response: {xml_text[:200]}"])

        def _int(tag: str) -> int:
            el = root.find(f".//{tag}")
            try:
                return int(el.text.strip()) if el is not None and el.text else 0
            except ValueError:
                return 0

        error_details = [
            el.text.strip()
            for el in root.findall(".//LINEERROR")
            if el.text and el.text.strip() and "retry split" not in el.text.lower()
        ]

        return TallyVoucherResult(
            created=_int("CREATED"),
            altered=_int("ALTERED"),
            errors=_int("ERRORS"),
            error_details=error_details,
        )

    @staticmethod
    def _format_date(date_str: str | None) -> str:
        """Convert YYYY-MM-DD → YYYYMMDD. Falls back to today on failure."""
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")
            except ValueError:
                pass
        return date.today().strftime("%Y%m%d")

    @staticmethod
    def _guess_counterpart_ledger(description: str, default: str) -> str:
        """Match description against known keywords; falls back to default ledger."""
        desc_lower = description.lower()
        for pattern, ledger in _LEDGER_KEYWORDS:
            if re.search(pattern, desc_lower):
                return ledger
        return default
