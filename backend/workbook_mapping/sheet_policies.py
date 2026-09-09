"""Known Industrial Template v27 sheet policies (structure-level).

Cell-level classification still inspects the workbook; these policies set
sheet role, write policy, and HAP fill priority consistently across the suite.
"""

from __future__ import annotations

from workbook_mapping.models import FillPriority, SheetRole, WritePolicy

# Exact sheet names as in the workbook (including trailing space on IC sheet).
SHEET_POLICIES: dict[str, dict[str, str]] = {
    "Balance Sheet - Standardized": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.HYBRID.value,
        "fill_priority": FillPriority.P0.value,
        "purpose": "Annual standardized balance sheet — primary BS data grid for HAP fill.",
    },
    "BS%": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "BS common-size percentages driven by Balance Sheet - Standardized.",
    },
    "Income - GAAP": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.HYBRID.value,
        "fill_priority": FillPriority.P0.value,
        "purpose": "Annual GAAP income statement — primary IS data grid for HAP fill.",
    },
    "IS%": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "IS common-size percentages driven by Income - GAAP.",
    },
    "Cash Flow - Standardized": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.HYBRID.value,
        "fill_priority": FillPriority.P0.value,
        "purpose": "Annual standardized cash flow — primary CF data grid for HAP fill.",
    },
    "CF%": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "CF percentages driven by Cash Flow - Standardized.",
    },
    "FCF": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Free cash flow build (formula-driven).",
    },
    "Last Quarter BS Standardized": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.HYBRID.value,
        "fill_priority": FillPriority.P1.value,
        "purpose": "LQ standardized balance sheet (deferred fill after annual path).",
    },
    "Last Quarter IS Standardized": {
        "role": SheetRole.HYBRID.value,
        "write_policy": WritePolicy.HYBRID.value,
        "fill_priority": FillPriority.P1.value,
        "purpose": "LQ standardized income statement (deferred fill).",
    },
    "Last Quarter CF Standardized": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.HYBRID.value,
        "fill_priority": FillPriority.P1.value,
        "purpose": "LQ standardized cash flow (deferred fill).",
    },
    "Last Quarter BS As Reported": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "LQ BS as-reported — company presentation; treat as historical, do not map in v0.",
    },
    "Last Quarter IS As Reported": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "LQ IS as-reported — historical / presentation; do not map in v0.",
    },
    "Last Quarter CF As Reported": {
        "role": SheetRole.DATA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "LQ CF as-reported — historical / presentation; do not map in v0.",
    },
    "DividendHelper": {
        "role": SheetRole.HELPER.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Dividend helper support sheet.",
    },
    "Inputs": {
        "role": SheetRole.HYBRID.value,
        "write_policy": WritePolicy.HYBRID.value,
        "fill_priority": FillPriority.P0.value,
        "purpose": (
            "Central bridge — formula-driven plus writable sinks for tax / PE10 / current data."
        ),
    },
    "IC & NOPAT & ROIC ": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Invested capital / NOPAT / ROIC (note trailing space in name).",
    },
    "Tax": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Tax / ETR support.",
    },
    "Leases": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Lease adjustments.",
    },
    "R&D": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "R&D capitalization adjustments.",
    },
    "All Ratios": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Ratio library from Inputs.",
    },
    "Final Metrics": {
        "role": SheetRole.FORMULA.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Summary metrics hub.",
    },
    "Expected Returns & Buybacks": {
        "role": SheetRole.OUTPUT.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Expected returns / buybacks outputs.",
    },
    "Enterprise Value": {
        "role": SheetRole.OUTPUT.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Enterprise value outputs.",
    },
    "Template Version": {
        "role": SheetRole.META.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": "Template version metadata.",
    },
}

# Annual statement sheets where period numeric constants are Writable Input candidates.
ANNUAL_DATA_SHEETS = frozenset(
    {
        "Income - GAAP",
        "Balance Sheet - Standardized",
        "Cash Flow - Standardized",
    }
)

LQ_STANDARDIZED_SHEETS = frozenset(
    {
        "Last Quarter BS Standardized",
        "Last Quarter IS Standardized",
        "Last Quarter CF Standardized",
    }
)

AS_REPORTED_SHEETS = frozenset(
    {
        "Last Quarter BS As Reported",
        "Last Quarter IS As Reported",
        "Last Quarter CF As Reported",
    }
)

# Quarterly update: leave exactly as current template — never carry, fill, or validate.
IGNORED_TEMPLATE_SHEETS = frozenset(
    AS_REPORTED_SHEETS
    | {
        "DividendHelper",
        "Dividend Helper",
    }
)

OUTPUT_SHEETS = frozenset(
    {
        "Expected Returns & Buybacks",
        "Enterprise Value",
        "Final Metrics",
        "All Ratios",
        "FCF",
    }
)

# Period data typically starts at column C (3) on annual statements.
PERIOD_DATA_START_COL = 3
# Label columns
LABEL_COLS = frozenset({1, 2})
# Control rows on annual statements
CONTROL_ROWS = frozenset({1, 2, 3})
HEADER_ROWS = frozenset({7, 8})  # FY labels / period end dates on annual sheets


def policy_for(sheet_name: str) -> dict[str, str]:
    if sheet_name in SHEET_POLICIES:
        return SHEET_POLICIES[sheet_name]
    return {
        "role": SheetRole.HYBRID.value,
        "write_policy": WritePolicy.READ_ONLY.value,
        "fill_priority": FillPriority.NEVER.value,
        "purpose": f"Unlisted sheet '{sheet_name}' — default read-only until classified.",
    }
