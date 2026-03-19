"""Standalone test script for the rule-based classifier.

Run with:
    python -m backend.scripts.test_classifier
"""

from __future__ import annotations

import asyncio
import json

from backend.services.classifier_service import classify_transaction


SAMPLE_TRANSACTIONS: list[tuple[str, float]] = [
    # 1. Salary credit — inflow triggers expense-inflow validation flag
    ("SALARY CREDIT MARCH 2024", 75_000.0),
    # 2. Rent payment — outflow, high confidence
    ("RENT PAYMENT TO LANDLORD FEB", -25_000.0),
    # 3. GST payment — Duties & Taxes, outflow
    ("GST PAYMENT Q3 2024", -18_000.0),
    # 4. EMI payment — Loans Liability, outflow
    ("EMI DEBIT HOME LOAN MARCH", -15_000.0),
    # 5. Electricity bill — Indirect Expenses, outflow
    ("ELECTRICITY BILL BESCOM MARCH", -3_500.0),
    # 6. Interest received — Indirect Income, inflow, valid
    ("INTEREST RECEIVED ON FD MARCH", 2_100.0),
    # 7. NEFT outflow → Sundry Creditors
    ("NEFT/000123/RAHUL TRADERS", -50_000.0),
    # 8. UPI inflow → Sundry Debtors
    ("UPI CREDIT FROM CUSTOMER PAYMENTS", 12_000.0),
    # 9. Suspense fallback — no keyword match
    ("MISCELLANEOUS DEBIT REF 9988776", -500.0),
    # 10. Dividend income — Indirect Income, inflow
    ("DIVIDEND CREDIT HDFC MUTUAL FUND", 4_500.0),
    # 11. No keyword/channel match → triggers GPT-4o Mini fallback (outflow)
    ("RANDOM XYZ DEBIT 12345", -999.0),
    # 12. No keyword/channel match → triggers GPT-4o Mini fallback (inflow)
    ("CREDIT FROM UNKNOWN SOURCE ABC", 5_000.0),
]


async def main() -> None:
    print("=" * 70)
    print("Transaction Classifier — Test Run")
    print("=" * 70)

    for idx, (narration, amount) in enumerate(SAMPLE_TRANSACTIONS, start=1):
        result = await classify_transaction(narration, amount)
        print(f"\n[{idx}] {narration!r}  (amount={amount:+,.2f})")
        print(json.dumps(result.model_dump(), indent=4))

    print("\n" + "=" * 70)
    print(f"Done — {len(SAMPLE_TRANSACTIONS)} transactions classified.")


if __name__ == "__main__":
    asyncio.run(main())
