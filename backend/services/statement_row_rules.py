"""Workbook rows <-> SEC tags for statement lines whose Bloomberg label is not the obvious one.

Each mapping was chosen by testing candidate rows against the values the supplied workbooks already hold (about 15
real companies): "LT Borrowings" agrees with LongTermDebtNoncurrent in 99% of values, "Acq of Fixed Prod Assets" with
PaymentsToAcquirePropertyPlantAndEquipment in 98%. Rows that did not agree (for example "LT Debt", about 34%) are
deliberately absent: a wrong row would put a wrong number into the analyst's workbook.

``sign`` converts the filing figure to the workbook convention (Bloomberg shows cash outflows as negative numbers).
"""

from __future__ import annotations

from typing import Any

STATEMENT_ROW_RULES: dict[str, dict[str, Any]] = {
    "debt": {
        "sheet": "Balance Sheet - Standardized",
        "needles": ("lt borrowings",),
        "tags": ("LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"),
        "sign": 1,
    },
    "capex": {
        "sheet": "Cash Flow - Standardized",
        "needles": ("acq of fixed prod assets",),
        "tags": ("PaymentsToAcquirePropertyPlantAndEquipment",),
        "sign": -1,
    },
}


def sign_for(concept: str) -> int:
    return int(STATEMENT_ROW_RULES.get(concept, {}).get("sign", 1))
