"""Industrial Template Inputs-bridge series (tax / PE10 / current)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from canonical_model.primitives import FinancialSeries


def _series(name: str) -> FinancialSeries:
    return FinancialSeries(name=name, currency="USD")


class InputsBridge(BaseModel):
    """
    Canonical Inputs-tab fields for Mode A completion.

    Historical series use FY tokens (FY2016…). Current_* scalars are point-in-time.
    """

    pe10: FinancialSeries = Field(default_factory=lambda: _series("PE10"))
    e10: FinancialSeries = Field(default_factory=lambda: _series("E10"))
    tax_federal: FinancialSeries = Field(default_factory=lambda: _series("Federal Tax"))
    tax_state: FinancialSeries = Field(default_factory=lambda: _series("State Taxes"))
    tax_foreign: FinancialSeries = Field(default_factory=lambda: _series("Foreign Taxes"))
    tax_expense: FinancialSeries = Field(
        default_factory=lambda: _series("Income Tax Expense")
    )
    # Unit switch: 0 = USD millions, 1 = percentage (template Inputs!E106)
    tax_unit_flag: int | None = 0
    current_price: float | None = None
    current_price_source: str | None = None
    current_e10: float | None = None
    current_pe10: float | None = None
    current_max_pe10: float | None = None
    max_price_to_buy: float | None = None
    exit_price_1: float | None = None
    expected_return_current: float | None = None
    expected_return_div_current: float | None = None
    expected_return_div_max_entry: float | None = None
    pe10_percentile: float | None = None
    current_eps_3y_10y_growth: float | None = None
    current_eps_growth_direction: str | None = None
    current_revenue_3y_10y_growth: float | None = None

    def series_for(self, field: str) -> FinancialSeries:
        series = getattr(self, field, None)
        if not isinstance(series, FinancialSeries):
            raise AttributeError(field)
        return series

    def scalar_for(self, field: str) -> Any:
        return getattr(self, field, None)
