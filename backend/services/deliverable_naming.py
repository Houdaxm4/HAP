"""Completed-workbook Excel names follow the period actually incorporated."""

from __future__ import annotations


def excel_deliverable_name(
    *,
    fiscal_year: int,
    ticker: str,
    analysis_type: str,
    fiscal_quarter: int | None = None,
) -> str:
    """Return the Excel deliverable filename for a newly generated analysis (FA = financial analysis).

    Quarterly workbooks use ``<YEAR> Q<QUARTER> <TICKER> FA.xlsx``; a fiscal-year (Q4) analysis uses ``<YEAR> FY <TICKER> FA.xlsx``.
    The analysis type is no longer part of the name. ``fiscal_year`` is the company's fiscal-year label, not the calendar year.
    """
    return f"{period_label(fiscal_year, fiscal_quarter)} {ticker.strip().upper()} FA.xlsx"


def period_label(fiscal_year: int, fiscal_quarter: int | None = None) -> str:
    """'2026 Q2' for a quarter, '2026 FY' for the fiscal year (Q4 is reported as FY)."""
    if fiscal_quarter and int(fiscal_quarter) in (1, 2, 3):
        return f"{fiscal_year} Q{int(fiscal_quarter)}"
    return f"{fiscal_year} FY"


def email_deliverable_name(*, fiscal_year: int, ticker: str, fiscal_quarter: int | None = None) -> str:
    """Base name of the email draft files: '2026 Q2 IDCC Email'."""
    return f"{period_label(fiscal_year, fiscal_quarter)} {ticker.strip().upper()} Email"
