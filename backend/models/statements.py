"""Financial statement extraction models (Balance Sheet, Income Statement, Cash Flow only)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.common import utc_now_iso

StatementType = Literal["balance_sheet", "income_statement", "cash_flow"]


class ExtractStatementsRequest(BaseModel):
    """Request to extract the three primary financial statements for a ticker."""

    ticker: str
    max_annual_periods: int = Field(default=10, ge=1, le=20)
    max_quarterly_periods: int = Field(default=8, ge=0, le=20)
    include_quarters: bool = True


class StatementValue(BaseModel):
    """One reported value for a statement line item."""

    period: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    value: float | None = None
    unit: str | None = None
    form: str | None = None
    filed: str | None = None
    accession_number: str | None = None
    frame: str | None = None


class StatementLineItem(BaseModel):
    """One line on a financial statement."""

    concept: str
    label: str
    xbrl_tag: str
    taxonomy: str = "us-gaap"
    section: str | None = None
    values: list[StatementValue] = Field(default_factory=list)


class FinancialStatement(BaseModel):
    """A single primary financial statement (no ratios)."""

    statement_type: StatementType
    title: str
    periods: list[str] = Field(default_factory=list)
    line_items: list[StatementLineItem] = Field(default_factory=list)
    line_item_count: int = 0
    populated_value_count: int = 0


class FinancialStatementsResult(BaseModel):
    """
    Extracted Balance Sheet, Income Statement, and Cash Flow only.

    No ratios. No analysis. No valuation metrics.
    """

    extraction_id: str
    ticker: str
    cik: str
    company_name: str | None = None
    source: str = "sec_company_facts"
    balance_sheet: FinancialStatement
    income_statement: FinancialStatement
    cash_flow: FinancialStatement
    annual_periods: list[str] = Field(default_factory=list)
    quarterly_periods: list[str] = Field(default_factory=list)
    extracted_at: str = Field(default_factory=utc_now_iso)
    message: str = (
        "Extracted Balance Sheet, Income Statement, and Cash Flow only. "
        "No ratios or analysis performed."
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
