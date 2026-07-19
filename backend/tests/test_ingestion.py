"""Tests for CompanyFinancialModelBuilder and AnalysisEngine."""

from __future__ import annotations

from ingestion.analysis_engine import AnalysisEngine
from ingestion.company_financial_model_builder import CompanyFinancialModelBuilder
from ingestion.custom_run_parser import CustomRunParser


def test_builder_and_analysis_engine(sample_custom_run_workbook, mock_company_facts, mock_filings_manifest):
    custom_run = CustomRunParser().parse(sample_custom_run_workbook, "custom_run_filter.xlsx")
    model = CompanyFinancialModelBuilder().build(
        analysis_id="test",
        ticker="AAPL",
        custom_run=custom_run,
        company_facts=mock_company_facts,
        filings_manifest=mock_filings_manifest,
        cik="0000320193",
    )

    assert model.ticker == "AAPL"
    assert model.market_data["Share Price"] == 195.5
    assert len(model.historical_metrics) == 3
    assert len(model.sec_statement_values) >= 1

    result = AnalysisEngine().run(model)
    assert result.status == "accepted"
    assert result.ticker == "AAPL"
