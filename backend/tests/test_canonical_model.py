"""Unit tests for the canonical financial model package."""

from __future__ import annotations

from canonical_model import (
    BalanceSheet,
    CashFlowStatement,
    CompanyFinancialModel,
    CompanyFinancialModelBuilder,
    FinancialPoint,
    FinancialSeries,
    IncomeStatement,
    MarketData,
    PeriodAmount,
    ValuationInputs,
)


def test_canonical_model_types_compose() -> None:
    model = CompanyFinancialModel(
        analysis_id="x",
        ticker="MSFT",
        income_statement=IncomeStatement(),
        balance_sheet=BalanceSheet(),
        cash_flow_statement=CashFlowStatement(),
        market_data=MarketData(share_price=400.0),
        valuation_inputs=ValuationInputs(wacc=0.08, tax_rate=0.21),
    )
    assert model.market_data.share_price == 400.0
    assert model.valuation_inputs.wacc == 0.08
    assert model.cash_flow_statement.free_cash_flow.is_empty
    assert isinstance(model.income_statement.net_income, FinancialSeries)


def test_financial_point_accepts_legacy_unit_alias() -> None:
    point = PeriodAmount(period="FY2024", value=10.0, unit="EUR", confidence=0.9)
    assert isinstance(point, FinancialPoint)
    assert point.currency == "EUR"
    assert point.unit == "EUR"


def test_financial_series_trend_helpers() -> None:
    series = FinancialSeries(name="Net Income", currency="USD")
    for year, value in [
        ("FY2020", 100.0),
        ("FY2021", 110.0),
        ("FY2022", 121.0),
        ("FY2023", 133.1),
        ("FY2024", 146.41),
    ]:
        series.upsert(
            FinancialPoint(
                period=year,
                value=value,
                currency="USD",
                source="SEC",
                confidence=0.9,
                audited=True,
            )
        )

    assert series.average(5) is not None
    assert series.cagr(5) is not None
    assert abs((series.cagr(5) or 0) - 0.1) < 0.001
    assert series.stability(5) is not None
    assert series.trend_direction(5) == "up"


def test_builder_class_api_populates_series() -> None:
    model = CompanyFinancialModelBuilder().build(
        analysis_id="x",
        ticker="MSFT",
        workbook_cells=[
            {
                "concept": "Revenue",
                "period": "FY2023",
                "value": 200_000_000_000,
                "cell_ref": "IS!B5",
                "confidence": 0.9,
                "audited": True,
                "source": "10-K",
            },
            {
                "concept": "Revenue",
                "period": "FY2024",
                "value": 245_000_000_000,
                "cell_ref": "IS!C5",
                "confidence": 0.95,
                "audited": True,
                "filing_type": "10-K",
            },
        ],
    )
    revenue = model.income_statement.revenue
    assert isinstance(revenue, FinancialSeries)
    assert len(revenue) == 2
    latest = revenue.latest()
    assert latest is not None
    assert latest.value == 245_000_000_000
    assert latest.audited is True
    assert latest.provenance is not None
    assert latest.provenance.cell_ref == "IS!C5"
    assert revenue.trend_direction() == "up"
