"""Tests for Financial Statement Extractor (BS / IS / CF only)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.statements import ExtractStatementsRequest
from services.statement_extractor import FinancialStatementExtractor, StatementExtractorError


def _company_facts() -> dict:
    return {
        "entityName": "Apple Inc.",
        "cik": 320193,
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {"val": 100, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2023-11-01", "accn": "a"},
                            {"val": 120, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                            {"val": 30, "fy": 2024, "fp": "Q1", "form": "10-Q", "filed": "2024-02-01", "accn": "c"},
                        ]
                    },
                },
                "NetIncomeLoss": {
                    "label": "Net Income",
                    "units": {
                        "USD": [
                            {"val": 20, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2023-11-01", "accn": "a"},
                            {"val": 25, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
                "Assets": {
                    "label": "Assets",
                    "units": {
                        "USD": [
                            {"val": 300, "fy": 2023, "fp": "FY", "form": "10-K", "filed": "2023-11-01", "accn": "a"},
                            {"val": 350, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
                "Liabilities": {
                    "label": "Liabilities",
                    "units": {
                        "USD": [
                            {"val": 150, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
                "StockholdersEquity": {
                    "label": "Equity",
                    "units": {
                        "USD": [
                            {"val": 200, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "label": "Operating Cash Flow",
                    "units": {
                        "USD": [
                            {"val": 40, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "label": "Capex",
                    "units": {
                        "USD": [
                            {"val": 8, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
                "NetCashProvidedByUsedInInvestingActivities": {
                    "label": "Investing Cash Flow",
                    "units": {
                        "USD": [
                            {"val": -10, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
                "NetCashProvidedByUsedInFinancingActivities": {
                    "label": "Financing Cash Flow",
                    "units": {
                        "USD": [
                            {"val": -15, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "accn": "b"},
                        ]
                    },
                },
            }
        },
    }


@pytest.fixture
def extractor() -> FinancialStatementExtractor:
    service = MagicMock()
    service.resolve_cik.return_value = "0000320193"
    service.fetch_company_facts.return_value = _company_facts()
    return FinancialStatementExtractor(sec_service=service)


def test_extracts_only_three_statements(extractor: FinancialStatementExtractor):
    result = extractor.extract(ExtractStatementsRequest(ticker="AAPL", include_quarters=True))

    assert result.ticker == "AAPL"
    assert result.cik == "0000320193"
    assert result.balance_sheet.statement_type == "balance_sheet"
    assert result.income_statement.statement_type == "income_statement"
    assert result.cash_flow.statement_type == "cash_flow"
    assert "No ratios or analysis" in result.message

    # Ensure no ratio-like statement types exist on the payload.
    payload = result.to_dict()
    assert set(payload.keys()) >= {
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "annual_periods",
        "quarterly_periods",
    }
    assert "ratios" not in payload
    assert "analysis" not in payload
    assert "valuation" not in payload


def test_income_statement_values_and_periods(extractor: FinancialStatementExtractor):
    result = extractor.extract(ExtractStatementsRequest(ticker="AAPL"))
    revenue = next(
        item for item in result.income_statement.line_items if item.concept == "revenue"
    )
    assert revenue.xbrl_tag == "Revenues"
    by_period = {value.period: value.value for value in revenue.values}
    assert by_period["FY2024"] == 120
    assert by_period["FY2023"] == 100
    assert "FY2024" in result.annual_periods
    assert result.income_statement.populated_value_count > 0


def test_balance_sheet_and_cash_flow_populated(extractor: FinancialStatementExtractor):
    result = extractor.extract(ExtractStatementsRequest(ticker="AAPL", include_quarters=False))
    assets = next(item for item in result.balance_sheet.line_items if item.concept == "total_assets")
    assert assets.values[-1].value == 350

    ocf = next(
        item for item in result.cash_flow.line_items if item.concept == "operating_cash_flow"
    )
    assert ocf.values[0].value == 40
    assert result.quarterly_periods == []


def test_unknown_ticker_raises(extractor: FinancialStatementExtractor):
    extractor.sec_service.resolve_cik.side_effect = Exception("Could not resolve CIK for ticker 'ZZZZ'.")
    # SecService raises SecServiceError; simulate via side_effect type used by extractor.
    from services.sec_service import SecServiceError

    extractor.sec_service.resolve_cik.side_effect = SecServiceError("Could not resolve CIK for ticker 'ZZZZ'.")
    with pytest.raises(StatementExtractorError, match="Could not resolve CIK"):
        extractor.extract(ExtractStatementsRequest(ticker="ZZZZ"))
