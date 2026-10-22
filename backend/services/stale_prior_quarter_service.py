"""A new company's workbook has no previous period, so the prior-quarter column of the Last Quarter BS tab must be empty.

The Industrial Template ships with that column (D) filled by the live pull: the quarter before the template's own latest one, i.e. a balance
sheet dated years AFTER a back-tested period (TPL 2019 Q4 carried Q1 2026). Left in place it feeds the quarter-over-quarter lines of the
email ("Equity -67.09%") and leaks future data into a point-in-time file. When column D is not earlier than column C, its hard-coded values
are cleared, its labels say so, and the formulas that divide by it show n/a. Every change is written to the HAP Adjustments tab.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from services.adjustment_ledger_service import AdjustmentLedger

LQ_BS = "Last Quarter BS Standardized"
_REF_D = re.compile(r"(?<![A-Za-z$])\$?D\$?\d+")


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
        if m:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def prior_quarter_is_earlier(ws) -> bool:
    """True when the prior-quarter column (D) is dated before the quarter column (C); when a date is missing it is not usable."""
    current, prior = _as_date(ws.cell(4, 3).value), _as_date(ws.cell(4, 4).value)
    return bool(current and prior and prior < current)


def clear_stale_prior_quarter(workbook_path: Path) -> dict[str, Any]:
    wb = load_workbook(workbook_path)
    try:
        if LQ_BS not in wb.sheetnames:
            return {"cleared": 0, "reason": "no Last Quarter BS tab"}
        ws = wb[LQ_BS]
        if prior_quarter_is_earlier(ws):
            return {"cleared": 0, "reason": "prior-quarter column is earlier than the quarter: kept"}
        stale_label, stale_date = ws.cell(5, 4).value, ws.cell(4, 4).value
        cleared = 0
        for r in range(1, (ws.max_row or 1) + 1):
            cell = ws.cell(r, 4)
            v = cell.value
            if v is None or (isinstance(v, str) and v.startswith("=")):
                continue
            cell.value = None
            cleared += 1
        ws["D2"] = "n/a"
        ws["D5"] = "Prior-quarter balance sheet not loaded"
        ws["D8"] = "n/a"
        wrapped = 0
        for row in ws.iter_rows(min_col=6, max_col=ws.max_column or 6):
            for cell in row:
                f = cell.value
                if isinstance(f, str) and f.startswith("=") and not f.upper().startswith("=IFERROR(") and _REF_D.search(f):
                    cell.value = '=IFERROR(' + f[1:] + ',"n/a")'
                    wrapped += 1
        ledger = AdjustmentLedger(wb)
        ledger.record(
            sheet=LQ_BS, cell="D4", fiscal_year=None, category="Point-in-time",
            what="Prior-quarter balance sheet column cleared",
            original=f"{cleared} values dated {str(stale_date)[:10]} ({stale_label})", new="blank (n/a)", amount=None,
            reason="The template's prior-quarter column held a balance sheet dated after this analysis' period; a new company has no previous period. "
                   f"{wrapped} formulas that divide by it now show n/a.",
            source="template", method="deterministic", confidence="high", mark_cell=False,
        )
        wb.save(workbook_path)
        return {"cleared": cleared, "wrapped_formulas": wrapped, "stale_date": str(stale_date)[:10]}
    finally:
        wb.close()
