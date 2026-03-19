"""GPT-4o Mini fallback for transactions that reach the suspense layer."""

from __future__ import annotations

import json
import os

import openai

from backend.services.classifier_service import ALLOWED_GROUPS, SUSPENSE_FALLBACK

SYSTEM_PROMPT = """You are a highly strict and conservative Indian accountant with deep knowledge of Tally ERP 9 chart of accounts. Your job is to classify a bank transaction into exactly one ledger and group from Indian accounting standards.

RULES:
1. Reply ONLY with valid JSON — no markdown, no explanation, no extra text.
2. The "group" field MUST be one of these exact strings:
   "Direct Expenses", "Indirect Expenses", "Direct Income", "Indirect Income",
   "Sundry Debtors", "Sundry Creditors", "Loans (Liability)", "Duties & Taxes",
   "Bank Accounts", "Cash-in-Hand", "Current Assets", "Current Liabilities", "Capital Account"
3. Negative amounts are outflows (payments/debits); positive amounts are inflows (receipts/credits).
4. Be conservative: if unsure, use "Suspense Account" with group "Current Assets".
5. The "confidence" field must be "high", "medium", or "low".

OUTPUT FORMAT (strict JSON):
{"ledger_name": "...", "group": "...", "reason": "...", "confidence": "..."}

EXAMPLES:
narration: "NEFT PAYMENT TO VENDOR ABC TRADERS"
amount: -50000
{"ledger_name": "Abc Traders A/c", "group": "Sundry Creditors", "reason": "NEFT payment to vendor; routed to Sundry Creditors", "confidence": "medium"}

narration: "SALARY CREDIT APRIL 2024"
amount: 85000
{"ledger_name": "Salary", "group": "Indirect Expenses", "reason": "Salary payment keyword matched", "confidence": "high"}

narration: "UPI RECEIVED FROM CUSTOMER XYZ"
amount: 12000
{"ledger_name": "Xyz A/c", "group": "Sundry Debtors", "reason": "UPI inflow from customer; routed to Sundry Debtors", "confidence": "medium"}

narration: "GST PAYMENT JULY 2024"
amount: -18000
{"ledger_name": "GST Payable", "group": "Duties & Taxes", "reason": "GST payment keyword matched", "confidence": "high"}

narration: "INTEREST RECEIVED ON SAVINGS ACCOUNT"
amount: 350
{"ledger_name": "Interest Received", "group": "Indirect Income", "reason": "Interest income keyword matched", "confidence": "high"}

narration: "MISCELLANEOUS DEBIT 99887766"
amount: -500
{"ledger_name": "Suspense Account", "group": "Current Assets", "reason": "No identifiable pattern; routed to suspense", "confidence": "low"}
"""


async def classify_with_llm(
    narration: str, amount: float
) -> tuple[str, str, str, str]:
    """Return (ledger_name, group, reason, confidence) using GPT-4o Mini.

    Falls back to SUSPENSE_FALLBACK on any error.
    """
    ledger_fallback, group_fallback = SUSPENSE_FALLBACK

    try:
        client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=256,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f'narration: "{narration}"\namount: {amount}'},
            ],
        )
        content = response.choices[0].message.content or ""
        data = json.loads(content)

        ledger_name = str(data.get("ledger_name", ledger_fallback))
        group = str(data.get("group", group_fallback))
        reason = str(data.get("reason", "LLM returned no reason"))
        confidence = str(data.get("confidence", "low"))

        if group not in ALLOWED_GROUPS:
            return (
                ledger_fallback,
                group_fallback,
                f"LLM fallback failed: returned invalid group '{group}'",
                "low",
            )

        return ledger_name, group, f"[gpt-4o-mini] {reason}", confidence

    except json.JSONDecodeError as exc:
        return ledger_fallback, group_fallback, f"LLM fallback failed: JSON parse error — {exc}", "low"
    except openai.OpenAIError as exc:
        return ledger_fallback, group_fallback, f"LLM fallback failed: OpenAI error — {exc}", "low"
    except Exception as exc:  # noqa: BLE001
        return ledger_fallback, group_fallback, f"LLM fallback failed: {exc}", "low"
