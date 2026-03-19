"""Dummy ICICI Bank statement data for demo/testing — simulates real OCR output."""

from __future__ import annotations

from backend.models.transaction import StatementData, Transaction


def get_demo_statement() -> StatementData:
    """Return a realistic ICICI Bank business account statement for Feb 2026."""
    transactions = [
        # ── HIGH confidence (keyword rules) ──────────────────────────────────
        Transaction(
            date="2026-02-01",
            description="NEFT-IN/001234/HDFC0000001/NEXUS CAPITAL CONTRIBUTION",
            credit=1_000_000.0,
            balance=5_420_000.0,
        ),
        Transaction(
            date="2026-02-03",
            description="ACH DR-ICICI BANK-SALARY PROCESSING FEB 2026",
            debit=450_000.0,
            balance=4_970_000.0,
        ),
        Transaction(
            date="2026-02-05",
            description="NEFT-OUT/005678/SBIN0001234/KRISHNA PROPERTIES RENT",
            debit=95_000.0,
            balance=4_875_000.0,
        ),
        Transaction(
            date="2026-02-06",
            description="BIL/000789/BSES RAJDHANI PWR LTD/ELECTRICITY FEB26",
            debit=18_600.0,
            balance=4_856_400.0,
        ),
        Transaction(
            date="2026-02-07",
            description="SI/AIRTEL BROADBAND/INTERNET SUBSCRIPTION FEB 2026",
            debit=3_540.0,
            balance=4_852_860.0,
        ),
        Transaction(
            date="2026-02-08",
            description="ACH DR-LIC OF INDIA-PREMIUM POL 438891234 FEB 2026",
            debit=22_750.0,
            balance=4_830_110.0,
        ),
        Transaction(
            date="2026-02-10",
            description="BIL/001122/GST CHALLAN GSTIN 07AABCN1234K1ZP FEB26",
            debit=89_200.0,
            balance=4_740_910.0,
        ),
        Transaction(
            date="2026-02-11",
            description="ACH DR-INCOME TAX DEPT-TDS PAYMENT TAN DELB12345B",
            debit=28_500.0,
            balance=4_712_410.0,
        ),
        Transaction(
            date="2026-02-12",
            description="ACH DR-ICICI BANK-HOME LOAN EMI AC 3456789 FEB 2026",
            debit=52_184.0,
            balance=4_660_226.0,
        ),
        Transaction(
            date="2026-02-13",
            description="NEFT-OUT/006789/KARB0000123/CA SURESH SHARMA PROFESSIONAL FEES",
            debit=35_000.0,
            balance=4_625_226.0,
        ),
        Transaction(
            date="2026-02-14",
            description="POS/0001234/INDIAN OIL PETROL PUMP OKHLA",
            debit=5_800.0,
            balance=4_619_426.0,
        ),
        Transaction(
            date="2026-02-15",
            description="INT CREDIT ON SAVINGS ACCOUNT FEB 2026 ICICI BANK",
            credit=11_230.0,
            balance=4_630_656.0,
        ),
        Transaction(
            date="2026-02-16",
            description="DIV CR-ICICI PRUDENTIAL MF DIVIDEND FEB 2026",
            credit=6_480.0,
            balance=4_637_136.0,
        ),
        Transaction(
            date="2026-02-17",
            description="REFUND CR/IRCTC/TICKET REF TXN20260217 CANCELLED",
            credit=2_180.0,
            balance=4_639_316.0,
        ),
        Transaction(
            date="2026-02-18",
            description="DEPRECIATION PROVISION FY2526 ASSET BLOCK PLANT",
            debit=15_000.0,
            balance=4_624_316.0,
        ),
        # ── MEDIUM confidence (NEFT/UPI/IMPS/RTGS + party name) ──────────────
        Transaction(
            date="2026-02-19",
            description="NEFT-OUT/007890/HDFC0001234/SURESH TRADING CO INV991",
            debit=145_000.0,
            balance=4_479_316.0,
        ),
        Transaction(
            date="2026-02-20",
            description="UPI/CR/26019/MEGHNA ENTERPRISES/PAYMENT ADVANCE",
            credit=78_000.0,
            balance=4_557_316.0,
        ),
        Transaction(
            date="2026-02-21",
            description="IMPS/CMS/23480934/TO RAJESH KUMAR VENDORS",
            debit=46_200.0,
            balance=4_511_116.0,
        ),
        Transaction(
            date="2026-02-22",
            description="RTGS/RTGS0034441/FROM DELTA SYSTEMS PRIVATE LTD",
            credit=300_000.0,
            balance=4_811_116.0,
        ),
        Transaction(
            date="2026-02-23",
            description="NEFT-OUT/009234/SBIN0000001/SHREE OFFSET PRINTERS",
            debit=18_500.0,
            balance=4_792_616.0,
        ),
        Transaction(
            date="2026-02-24",
            description="UPI/CR/26054/FROM BHARAT PHARMA DISTRIBUTORS",
            credit=105_000.0,
            balance=4_897_616.0,
        ),
        Transaction(
            date="2026-02-25",
            description="IMPS/P2M/34552209/TO NEHA STATIONERY STORE INV088",
            debit=8_150.0,
            balance=4_889_466.0,
        ),
        # ── LOW confidence (LLM fallback) ─────────────────────────────────────
        Transaction(
            date="2026-02-26",
            description="MISC DR/INT ADJ INR Q2ADJ REF 4488220",
            debit=3_900.0,
            balance=4_885_566.0,
        ),
        Transaction(
            date="2026-02-27",
            description="MISC CR/CLG ADJ REF 8877665 BANK MEMO",
            credit=6_750.0,
            balance=4_892_316.0,
        ),
        Transaction(
            date="2026-02-28",
            description="CHQ/PDC/009812/HONRD CLG 28FEB2026",
            debit=26_500.0,
            balance=4_865_816.0,
        ),
    ]

    return StatementData(
        account_holder="Nexus Tech Solutions Pvt Ltd",
        bank_name="ICICI Bank",
        account_number="XXXX-XXXX-7291",
        transactions=transactions,
    )
