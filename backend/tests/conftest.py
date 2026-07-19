"""Shared pytest fixtures for HAP backend pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from ingestion.custom_run_schema import (
    SHEET_ASSUMPTIONS,
    SHEET_HISTORICAL_METRICS,
    SHEET_MARKET_DATA,
    SHEET_METADATA,
    SHEET_PROPRIETARY_METRICS,
    SHEET_QUALITY_METRICS,
    SHEET_VALUATION_METRICS,
)


def build_bloomberg_custom_run_workbook(path: Path, *, ticker: str = "AAPL") -> Path:
    """Build a standardized Bloomberg Custom_Run_Filter workbook for tests."""
    workbook = Workbook()
    workbook.remove(workbook.active)

    metadata = workbook.create_sheet(SHEET_METADATA)
    metadata.append(["Field", "Value"])
    metadata.append(["Ticker", ticker])
    metadata.append(["Company Name", "Apple Inc."])
    metadata.append(["Currency", "USD"])
    metadata.append(["Fiscal Year End", "September"])

    market = workbook.create_sheet(SHEET_MARKET_DATA)
    market.append(["Field", "Value"])
    market.append(["Share Price", 195.5])
    market.append(["Market Cap", 3000000000000])
    market.append(["Shares Outstanding", 15300000000])

    historical = workbook.create_sheet(SHEET_HISTORICAL_METRICS)
    historical.append(["Metric", "FY2023", "FY2024"])
    historical.append(["Revenue", 383285000000, 391035000000])
    historical.append(["Net Income", 96995000000, 93736000000])
    historical.append(["Total Assets", 352755000000, 364980000000])

    proprietary = workbook.create_sheet(SHEET_PROPRIETARY_METRICS)
    proprietary.append(["Metric", "FY2024"])
    proprietary.append(["ROIC", 0.45])
    proprietary.append(["FCF Yield", 0.035])

    valuation = workbook.create_sheet(SHEET_VALUATION_METRICS)
    valuation.append(["Metric", "Current"])
    valuation.append(["P/E Ratio", 28.5])
    valuation.append(["EV/EBITDA", 22.1])

    quality = workbook.create_sheet(SHEET_QUALITY_METRICS)
    quality.append(["Metric", "Score"])
    quality.append(["Business Quality Score", 8.5])
    quality.append(["Management Quality", 9.0])

    assumptions = workbook.create_sheet(SHEET_ASSUMPTIONS)
    assumptions.append(["Field", "Value"])
    assumptions.append(["Terminal Growth Rate", 0.03])
    assumptions.append(["WACC", 0.085])

    workbook.save(path)
    workbook.close()
    return path


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "fixtures"
    directory.mkdir()
    return directory


@pytest.fixture
def sample_workbook(fixtures_dir: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Income Statement"
    sheet["A1"] = "Metric"
    sheet["B1"] = "FY2024"
    sheet["A5"] = "Revenue"
    sheet["B5"] = None
    sheet["A6"] = "Net Income"
    sheet["B6"] = None
    sheet["A10"] = "Total"
    sheet["B10"] = "=SUM(B5:B6)"

    balance = workbook.create_sheet("Balance Sheet")
    balance["A1"] = "Metric"
    balance["B1"] = "FY2024"
    balance["A5"] = "Total Assets"
    balance["B5"] = None

    path = fixtures_dir / "prefilled_workbook.xlsx"
    workbook.save(path)
    workbook.close()
    return path


@pytest.fixture
def sample_custom_run_workbook(fixtures_dir: Path) -> Path:
    path = fixtures_dir / "custom_run_filter.xlsx"
    return build_bloomberg_custom_run_workbook(path, ticker="AAPL")


@pytest.fixture
def mock_company_facts() -> dict:
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [
                            {
                                "val": 391035000000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000123",
                            }
                        ]
                    },
                },
                "NetIncomeLoss": {
                    "label": "Net Income (Loss)",
                    "units": {
                        "USD": [
                            {
                                "val": 93736000000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000123",
                            }
                        ]
                    },
                },
                "Assets": {
                    "label": "Assets",
                    "units": {
                        "USD": [
                            {
                                "val": 364980000000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000123",
                            }
                        ]
                    },
                },
            }
        }
    }


@pytest.fixture
def mock_filings_manifest() -> dict:
    return {
        "ticker": "AAPL",
        "cik": "0000320193",
        "selected_filings": [
            {
                "accession_number": "0000320193-24-000123",
                "filing_type": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "primary_document": "aapl-20240928.htm",
                "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
                "fiscal_year": 2024,
            }
        ],
    }
