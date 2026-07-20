"""Tests for canonical financial model builder and analysis_engine wiring."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, ProfitabilityModule
from canonical_model import CompanyFinancialModel, FinancialSeries, build_company_financial_model


def _sample_cells() -> list[dict]:
    cells: list[dict] = []
    net_income = {
        "FY2020": 57_411_000_000,
        "FY2021": 94_680_000_000,
        "FY2022": 99_803_000_000,
        "FY2023": 96_995_000_000,
        "FY2024": 93_736_000_000,
    }
    equity = {
        "FY2020": 65_339_000_000,
        "FY2021": 63_090_000_000,
        "FY2022": 50_672_000_000,
        "FY2023": 62_146_000_000,
        "FY2024": 74_000_000_000,
    }
    assets = {
        "FY2020": 323_888_000_000,
        "FY2021": 351_002_000_000,
        "FY2022": 352_755_000_000,
        "FY2023": 352_583_000_000,
        "FY2024": 364_980_000_000,
    }
    operating_income = {
        "FY2020": 66_288_000_000,
        "FY2021": 108_949_000_000,
        "FY2022": 119_437_000_000,
        "FY2023": 114_301_000_000,
        "FY2024": 120_000_000_000,
    }
    invested_capital = {
        "FY2020": 400_000_000_000,
        "FY2021": 420_000_000_000,
        "FY2022": 450_000_000_000,
        "FY2023": 480_000_000_000,
        "FY2024": 500_000_000_000,
    }
    tax = {
        "FY2020": 9_680_000_000,
        "FY2021": 14_527_000_000,
        "FY2022": 19_300_000_000,
        "FY2023": 16_750_000_000,
        "FY2024": 24_000_000_000,
    }

    for period, value in net_income.items():
        cells.append(
            {
                "concept": "Net Income",
                "period": period,
                "value": value,
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
                "cell_ref": f"IS!NI_{period}",
            }
        )
    for period, value in equity.items():
        cells.append(
            {
                "concept": "Shareholders Equity",
                "period": period,
                "value": value,
                "confidence": 0.9,
                "audited": True,
                "cell_ref": f"BS!EQ_{period}",
            }
        )
    for period, value in assets.items():
        cells.append(
            {
                "concept": "Total Assets",
                "period": period,
                "value": value,
                "confidence": 0.91,
                "audited": True,
                "cell_ref": f"BS!TA_{period}",
            }
        )
    for period, value in operating_income.items():
        cells.append(
            {
                "concept": "Operating Income",
                "period": period,
                "value": value,
                "confidence": 0.88,
                "audited": True,
                "cell_ref": f"IS!OI_{period}",
            }
        )
    for period, value in invested_capital.items():
        cells.append(
            {
                "concept": "Invested Capital",
                "period": period,
                "value": value,
                "confidence": 0.8,
                "cell_ref": f"BS!IC_{period}",
            }
        )
    for period, value in tax.items():
        cells.append(
            {
                "concept": "Tax Expense",
                "period": period,
                "value": value,
                "confidence": 0.85,
                "cell_ref": f"IS!TAX_{period}",
            }
        )

    cells.extend(
        [
            {"concept": "WACC", "period": "FY2024", "value": 0.09, "cell_ref": "VAL!B2"},
            {"concept": "Share Price", "period": "FY2024", "value": 190.0, "cell_ref": "MKT!B1"},
        ]
    )
    return cells


def test_builder_maps_cells_into_historical_series() -> None:
    model = build_company_financial_model(
        analysis_id="a1",
        ticker="aapl",
        company="Apple Inc.",
        workbook_cells=_sample_cells(),
    )

    assert isinstance(model, CompanyFinancialModel)
    assert model.ticker == "AAPL"
    assert "FY2024" in model.periods
    assert isinstance(model.income_statement.net_income, FinancialSeries)
    assert len(model.income_statement.net_income) == 5
    assert model.income_statement.latest("net_income") is not None
    assert model.income_statement.latest("net_income").value == 93_736_000_000
    assert model.income_statement.latest("net_income").audited is True
    assert model.balance_sheet.latest("total_assets") is not None
    assert model.market_data.share_price == 190.0
    assert model.valuation_inputs.wacc == 0.09
    assert not hasattr(model, "workbook")
    assert not hasattr(model, "get_cell")


def test_builder_filters_failed_validation_cells() -> None:
    provenance = {
        "entries": [
            {
                "cell_ref": "IS!B5",
                "concept": "Revenue",
                "period": "FY2024",
                "value": 100,
                "status": "filled",
                "confidence": 0.9,
            },
            {
                "cell_ref": "IS!B6",
                "concept": "Net Income",
                "period": "FY2024",
                "value": 20,
                "status": "filled",
                "confidence": 0.9,
                "filing_type": "10-K",
            },
        ]
    }
    discrepancy = {
        "checks": [
            {"cell_ref": "IS!B5", "status": "fail"},
            {"cell_ref": "IS!B6", "status": "pass"},
        ]
    }
    model = build_company_financial_model(
        analysis_id="a3",
        ticker="TEST",
        provenance_report=provenance,
        discrepancy_report=discrepancy,
    )
    assert model.income_statement.revenue.is_empty
    assert model.income_statement.latest("net_income") is not None
    assert model.income_statement.latest("net_income").value == 20
    assert model.income_statement.latest("net_income").audited is True


def test_profitability_emits_score_contract() -> None:
    model = build_company_financial_model(
        analysis_id="a1",
        ticker="AAPL",
        workbook_cells=_sample_cells(),
        valuation_inputs={"wacc": 0.09},
    )
    result = ProfitabilityModule().analyze(model)

    assert result.module_name == "profitability"
    assert result.module_id == "profitability"
    assert result.status == "ok"
    assert result.score is not None
    assert 0 <= result.score <= 100
    codes = {metric.code for metric in result.metrics}
    assert {"ROE", "ROA", "ROIC"} <= codes
    assert result.component_scores
    dumped = result.model_dump()
    assert "report" not in dumped
    assert "narrative" not in dumped
    for finding in result.findings:
        assert finding.evidence


def test_profitability_skips_without_net_income() -> None:
    model = CompanyFinancialModel(analysis_id="a2", ticker="TEST")
    result = ProfitabilityModule().analyze(model)
    assert result.status == "skipped"
    assert result.error


def test_engine_runs_against_company_financial_model() -> None:
    model = build_company_financial_model(
        analysis_id="a1",
        ticker="AAPL",
        workbook_cells=_sample_cells(),
        valuation_inputs={"wacc": 0.09},
    )
    engine_result = AnalysisEngine().run(model)

    assert engine_result.summary_metrics["module_count"] == 10
    assert engine_result.summary_metrics["ok_count"] == 3
    assert engine_result.summary_metrics["skipped_count"] == 7
    assert engine_result.metrics
    assert engine_result.findings
    assert engine_result.business_quality is not None
    assert engine_result.investment_attractiveness is not None
    assert engine_result.recommendation is not None
    assert engine_result.summary_metrics["recommendation"] == engine_result.recommendation.recommendation
    profitability = next(m for m in engine_result.modules if m.module_name == "profitability")
    assert profitability.score is not None
    capital_allocation = next(
        m for m in engine_result.modules if m.module_name == "capital_allocation"
    )
    assert capital_allocation.status == "ok"
    assert capital_allocation.score is not None
    recommendation = next(m for m in engine_result.modules if m.module_name == "recommendation")
    assert recommendation.module_name == "recommendation"
    assert recommendation.coverage["recommendation_code"] == engine_result.recommendation.recommendation
