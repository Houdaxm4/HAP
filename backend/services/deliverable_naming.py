"""Completed-workbook Excel names follow the period actually incorporated."""

from __future__ import annotations


def excel_deliverable_name(
    *,
    fiscal_year: int,
    ticker: str,
    analysis_type: str,
    fiscal_quarter: int | None = None,
) -> str:
    """Return the Excel deliverable filename for a newly generated analysis.

    Quarterly workbooks use ``<YEAR> Q<QUARTER> <TICKER> <ANALYSIS_TYPE>.xlsx``.
    Annual workbooks use ``<YEAR> Fiscal Year <TICKER> <ANALYSIS_TYPE>.xlsx``.
    ``fiscal_year`` is the company's fiscal-year label, not the calendar year.
    """
    name = ticker.strip().upper()
    label = analysis_type.strip()
    if fiscal_quarter:
        return f"{fiscal_year} Q{int(fiscal_quarter)} {name} {label}.xlsx"
    return f"{fiscal_year} Fiscal Year {name} {label}.xlsx"
