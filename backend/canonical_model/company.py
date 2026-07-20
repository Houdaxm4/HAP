"""Top-level company financial model and market/valuation inputs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from canonical_model.statements import BalanceSheet, CashFlowStatement, IncomeStatement
from canonical_model.workbook_metrics import WorkbookMetricCatalog


class MarketData(BaseModel):
    """Observable market inputs used by valuation / expected-return modules."""

    currency: str = "USD"
    as_of_date: str | None = None
    share_price: float | None = None
    shares_outstanding: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    beta: float | None = None
    dividend_yield: float | None = None


class ValuationInputs(BaseModel):
    """Explicit valuation assumptions — separate from reported statements."""

    currency: str = "USD"
    risk_free_rate: float | None = None
    equity_risk_premium: float | None = None
    cost_of_equity: float | None = None
    cost_of_debt: float | None = None
    tax_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    wacc: float | None = None
    terminal_growth_rate: float | None = None
    forecast_years: int | None = Field(default=None, ge=1)
    net_debt: float | None = None
    minority_interest: float | None = None
    preferred_equity: float | None = None
    extras: dict[str, float] = Field(default_factory=dict)


class CompanyFinancialModel(BaseModel):
    """
    Canonical financial representation of a company for one HAP analysis.

    This is the only financial input the analysis engine may consume.
    It must never expose raw Excel workbook objects or cell-address APIs.
    """

    analysis_id: str
    ticker: str
    company: str | None = None
    analysis_type: str | None = None
    reporting_currency: str = "USD"
    periods: list[str] = Field(default_factory=list)
    income_statement: IncomeStatement = Field(default_factory=IncomeStatement)
    balance_sheet: BalanceSheet = Field(default_factory=BalanceSheet)
    cash_flow_statement: CashFlowStatement = Field(default_factory=CashFlowStatement)
    market_data: MarketData = Field(default_factory=MarketData)
    valuation_inputs: ValuationInputs = Field(default_factory=ValuationInputs)
    workbook_metrics: WorkbookMetricCatalog = Field(default_factory=WorkbookMetricCatalog)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def refresh_periods(self) -> None:
        """Recompute the union of periods across all statements."""
        merged = set(self.periods)
        merged.update(self.income_statement.periods())
        merged.update(self.balance_sheet.periods())
        merged.update(self.cash_flow_statement.periods())
        self.periods = sorted(merged)
