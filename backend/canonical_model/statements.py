"""Canonical financial statement models backed by FinancialSeries."""

from __future__ import annotations

from pydantic import BaseModel, Field

from canonical_model.primitives import FinancialPoint, FinancialSeries


def _series(name: str) -> FinancialSeries:
    return FinancialSeries(name=name)


def _periods(*series: FinancialSeries) -> list[str]:
    found: set[str] = set()
    for item in series:
        found.update(item.periods())
    return sorted(found)


class IncomeStatement(BaseModel):
    """Canonical income statement as historical series."""

    currency: str = "USD"
    revenue: FinancialSeries = Field(default_factory=lambda: _series("Revenue"))
    cost_of_revenue: FinancialSeries = Field(default_factory=lambda: _series("Cost of Revenue"))
    gross_profit: FinancialSeries = Field(default_factory=lambda: _series("Gross Profit"))
    operating_income: FinancialSeries = Field(default_factory=lambda: _series("Operating Income"))
    ebit: FinancialSeries = Field(default_factory=lambda: _series("EBIT"))
    ebitda: FinancialSeries = Field(default_factory=lambda: _series("EBITDA"))
    interest_expense: FinancialSeries = Field(default_factory=lambda: _series("Interest Expense"))
    tax_expense: FinancialSeries = Field(default_factory=lambda: _series("Tax Expense"))
    net_income: FinancialSeries = Field(default_factory=lambda: _series("Net Income"))
    diluted_eps: FinancialSeries = Field(default_factory=lambda: _series("Diluted EPS"))

    def series_for(self, field: str) -> FinancialSeries:
        value = getattr(self, field)
        if not isinstance(value, FinancialSeries):
            raise AttributeError(f"{field} is not a FinancialSeries")
        return value

    def latest(self, field: str) -> FinancialPoint | None:
        return self.series_for(field).latest()

    def value_for(self, field: str, period: str) -> float | None:
        return self.series_for(field).value_for(period)

    def periods(self) -> list[str]:
        return _periods(
            self.revenue,
            self.cost_of_revenue,
            self.gross_profit,
            self.operating_income,
            self.ebit,
            self.ebitda,
            self.interest_expense,
            self.tax_expense,
            self.net_income,
            self.diluted_eps,
        )


class BalanceSheet(BaseModel):
    """Canonical balance sheet as historical series."""

    currency: str = "USD"
    cash: FinancialSeries = Field(default_factory=lambda: _series("Cash"))
    current_assets: FinancialSeries = Field(default_factory=lambda: _series("Current Assets"))
    total_assets: FinancialSeries = Field(default_factory=lambda: _series("Total Assets"))
    current_liabilities: FinancialSeries = Field(
        default_factory=lambda: _series("Current Liabilities")
    )
    total_liabilities: FinancialSeries = Field(default_factory=lambda: _series("Total Liabilities"))
    total_debt: FinancialSeries = Field(default_factory=lambda: _series("Total Debt"))
    shareholders_equity: FinancialSeries = Field(
        default_factory=lambda: _series("Shareholders Equity")
    )
    invested_capital: FinancialSeries = Field(default_factory=lambda: _series("Invested Capital"))

    def series_for(self, field: str) -> FinancialSeries:
        value = getattr(self, field)
        if not isinstance(value, FinancialSeries):
            raise AttributeError(f"{field} is not a FinancialSeries")
        return value

    def latest(self, field: str) -> FinancialPoint | None:
        return self.series_for(field).latest()

    def value_for(self, field: str, period: str) -> float | None:
        return self.series_for(field).value_for(period)

    def periods(self) -> list[str]:
        return _periods(
            self.cash,
            self.current_assets,
            self.total_assets,
            self.current_liabilities,
            self.total_liabilities,
            self.total_debt,
            self.shareholders_equity,
            self.invested_capital,
        )


class CashFlowStatement(BaseModel):
    """Canonical cash flow statement as historical series."""

    currency: str = "USD"
    operating_cash_flow: FinancialSeries = Field(
        default_factory=lambda: _series("Operating Cash Flow")
    )
    capital_expenditures: FinancialSeries = Field(
        default_factory=lambda: _series("Capital Expenditures")
    )
    free_cash_flow: FinancialSeries = Field(default_factory=lambda: _series("Free Cash Flow"))
    dividends: FinancialSeries = Field(default_factory=lambda: _series("Dividends"))
    share_repurchases: FinancialSeries = Field(default_factory=lambda: _series("Share Repurchases"))
    financing_cash_flow: FinancialSeries = Field(
        default_factory=lambda: _series("Financing Cash Flow")
    )
    investing_cash_flow: FinancialSeries = Field(
        default_factory=lambda: _series("Investing Cash Flow")
    )

    def series_for(self, field: str) -> FinancialSeries:
        value = getattr(self, field)
        if not isinstance(value, FinancialSeries):
            raise AttributeError(f"{field} is not a FinancialSeries")
        return value

    def latest(self, field: str) -> FinancialPoint | None:
        return self.series_for(field).latest()

    def value_for(self, field: str, period: str) -> float | None:
        return self.series_for(field).value_for(period)

    def periods(self) -> list[str]:
        return _periods(
            self.operating_cash_flow,
            self.capital_expenditures,
            self.free_cash_flow,
            self.dividends,
            self.share_repurchases,
            self.financing_cash_flow,
            self.investing_cash_flow,
        )
