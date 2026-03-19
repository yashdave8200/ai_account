"""Rule-based transaction classification service.

Pure stateless functions — no classes needed.
"""

from __future__ import annotations

import re
from typing import Literal

from backend.models.classifier import ClassificationResult

# ---------------------------------------------------------------------------
# Allowed Tally groups
# ---------------------------------------------------------------------------

ALLOWED_GROUPS: frozenset[str] = frozenset(
    {
        "Direct Expenses",
        "Indirect Expenses",
        "Direct Income",
        "Indirect Income",
        "Sundry Debtors",
        "Sundry Creditors",
        "Loans (Liability)",
        "Duties & Taxes",
        "Bank Accounts",
        "Cash-in-Hand",
        "Current Assets",
        "Current Liabilities",
        "Capital Account",
    }
)

_EXPENSE_GROUPS: frozenset[str] = frozenset(
    {"Direct Expenses", "Indirect Expenses"}
)

_INCOME_GROUPS: frozenset[str] = frozenset(
    {"Direct Income", "Indirect Income"}
)

SUSPENSE_FALLBACK: tuple[str, str] = ("Suspense Account", "Current Assets")

# ---------------------------------------------------------------------------
# Keyword rules: (regex, ledger_name, group, reason)
# First match wins — order matters.
# ---------------------------------------------------------------------------

KEYWORD_RULES: list[tuple[str, str, str, str]] = [
    # Salary
    (r"\bsalary\b|\bsal\b|\bpayroll\b", "Salary", "Indirect Expenses", "Salary payment keyword matched"),
    # Rent
    (r"\brent\b|\blease\b", "Rent", "Indirect Expenses", "Rent payment keyword matched"),
    # Electricity / utilities
    (r"\belectricity\b|\bpower\b|\bebill\b|\bbescom\b|\btangedco\b|\bmsedcl\b", "Electricity Charges", "Indirect Expenses", "Electricity bill keyword matched"),
    # Telephone / internet
    (r"\btelephone\b|\bmobile\b|\binternet\b|\bbroadband\b|\bbsnl\b|\bairtel\b|\bjio\b", "Telephone Charges", "Indirect Expenses", "Telephone/internet keyword matched"),
    # Insurance
    (r"\binsurance\b|\blic\b|\bpremium\b", "Insurance", "Indirect Expenses", "Insurance premium keyword matched"),
    # Professional fees
    (r"\bconsultancy\b|\bconsulting\b|\bprofessional\b|\baudit\b|\blegal\b|\badvocate\b", "Professional Fees", "Indirect Expenses", "Professional fees keyword matched"),
    # Fuel / conveyance
    (r"\bfuel\b|\bpetrol\b|\bdiesel\b|\bconveyance\b|\btravell?ing\b", "Fuel & Conveyance", "Indirect Expenses", "Fuel/conveyance keyword matched"),
    # Depreciation
    (r"\bdepreciation\b", "Depreciation", "Indirect Expenses", "Depreciation keyword matched"),
    # GST / tax payments (must come before bare "interest" check)
    (r"\bgst\b|\bigst\b|\bcgst\b|\bsgst\b", "GST Payable", "Duties & Taxes", "GST payment keyword matched"),
    # TDS
    (r"\btds\b|\btax deducted\b|\bincome tax\b", "TDS Payable", "Duties & Taxes", "TDS/tax keyword matched"),
    # Interest received — must be before bare "interest" rule
    (r"\binterest\s+received\b|\binterest\s+credit\b|\bint\s+cr\b", "Interest Received", "Indirect Income", "Interest income keyword matched"),
    # Interest expense
    (r"\binterest\b|\bint\b", "Interest on Loan", "Indirect Expenses", "Interest expense keyword matched"),
    # Dividend
    (r"\bdividend\b|\bdiv\b", "Dividend Income", "Indirect Income", "Dividend income keyword matched"),
    # Refund
    (r"\brefund\b", "Refund Received", "Indirect Income", "Refund keyword matched"),
    # EMI / loan repayment
    (r"\bemi\b|\bloan\s+repay\b|\bloan\s+instalment\b|\bloan\s+installment\b", "Loan EMI", "Loans (Liability)", "EMI/loan repayment keyword matched"),
    # Capital
    (r"\bcapital\b|\bequity\b|\bshare\s+capital\b", "Capital Account", "Capital Account", "Capital transaction keyword matched"),
]

# ---------------------------------------------------------------------------
# Payment channel detection
# ---------------------------------------------------------------------------

PAYMENT_CHANNEL_PATTERN: re.Pattern = re.compile(
    r"\b(NEFT|IMPS|UPI|RTGS)\b", re.IGNORECASE
)

# Ordered patterns to extract a party name from the narration.
# Each tuple: (compiled regex, group index to use as party name)
PARTY_NAME_EXTRACTORS: list[tuple[re.Pattern, int]] = [
    # "TO <NAME>" or "FROM <NAME>"
    (re.compile(r"\b(?:TO|FROM)\s+([A-Z][A-Z0-9 &./-]{2,})", re.IGNORECASE), 1),
    # "NEFT/RTGS/IMPS/UPI <channel-ref>/<NAME>"
    (re.compile(r"\b(?:NEFT|IMPS|UPI|RTGS)[/-]?\s*\w+[/-]\s*([A-Z][A-Z0-9 &.]{2,})", re.IGNORECASE), 1),
    # Last capitalised word-group of ≥3 chars after the channel keyword
    (re.compile(r"\b(?:NEFT|IMPS|UPI|RTGS)\b.*?([A-Z]{3,}(?:\s+[A-Z]{2,})*)\s*$", re.IGNORECASE), 1),
]


def _extract_party_name(narration: str) -> str | None:
    """Try each extractor in order; return first non-empty match."""
    for pattern, group in PARTY_NAME_EXTRACTORS:
        m = pattern.search(narration)
        if m:
            name = m.group(group).strip()
            if name:
                return name
    return None


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

def apply_rules(narration: str, amount: float) -> tuple[str, str, str, str]:
    """Return (ledger_name, group, reason, confidence).

    Priority:
    1. Keyword rules (first match) → confidence="high"
    2. Payment channel detected    → confidence="medium"/"low"
    3. Suspense fallback           → confidence="low"
    """
    norm = narration.lower()

    # Layer 1 — keyword rules
    for pattern, ledger, group, reason in KEYWORD_RULES:
        if re.search(pattern, norm):
            return ledger, group, reason, "high"

    # Layer 2 — payment channel
    if PAYMENT_CHANNEL_PATTERN.search(narration):
        party = _extract_party_name(narration)
        if party:
            ledger = f"{party.title()} A/c"
            group = "Sundry Creditors" if amount < 0 else "Sundry Debtors"
            reason = f"Payment channel detected; party '{party.title()}' extracted"
            return ledger, group, reason, "medium"
        else:
            group = "Sundry Creditors" if amount < 0 else "Sundry Debtors"
            reason = "Payment channel detected; no party name extracted"
            ledger = group
            return ledger, group, reason, "low"

    # Layer 3 — suspense fallback
    ledger, group = SUSPENSE_FALLBACK
    return ledger, group, "No matching rule found; routed to suspense", "low"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_transaction(
    ledger_name: str, group: str, amount: float
) -> tuple[Literal["valid", "flagged"], list[str]]:
    """Collect ALL validation failures and return status + notes."""
    notes: list[str] = []
    ln_lower = ledger_name.lower()

    if group not in ALLOWED_GROUPS:
        notes.append(f"Group '{group}' is not in the list of allowed Tally groups")

    if group in _EXPENSE_GROUPS and amount > 0:
        notes.append(
            f"Expense group '{group}' has a positive amount (inflow) — expected outflow"
        )

    if group in _INCOME_GROUPS and amount < 0:
        notes.append(
            f"Income group '{group}' has a negative amount (outflow) — expected inflow"
        )

    if re.search(r"\b(gst|igst|cgst|sgst)\b", ln_lower) and group != "Duties & Taxes":
        notes.append(
            f"Ledger '{ledger_name}' looks like a tax ledger but group is '{group}' (expected 'Duties & Taxes')"
        )

    if re.search(r"\b(emi|loan)\b", ln_lower) and group != "Loans (Liability)":
        notes.append(
            f"Ledger '{ledger_name}' looks like a loan ledger but group is '{group}' (expected 'Loans (Liability)')"
        )

    if notes:
        return "flagged", notes
    return "valid", []


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def classify_transaction(narration: str, amount: float) -> ClassificationResult:
    """Classify a single transaction and validate the result."""
    ledger_name, group, reason, confidence = apply_rules(narration, amount)

    # GPT-4o Mini fallback when rule engine routes to suspense
    if ledger_name == SUSPENSE_FALLBACK[0]:
        from backend.services.llm_fallback import classify_with_llm
        ledger_name, group, reason, confidence = await classify_with_llm(narration, amount)

    validation_status, validation_notes = validate_transaction(ledger_name, group, amount)

    return ClassificationResult(
        narration=narration,
        amount=amount,
        ledger_name=ledger_name,
        group=group,
        reason=reason,
        confidence=confidence,
        validation_status=validation_status,
        validation_notes=validation_notes,
    )
