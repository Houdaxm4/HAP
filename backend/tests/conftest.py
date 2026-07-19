"""Shared pytest fixtures for HAP backend pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from ingestion.production_workbook_profile import (
    PRODUCTION_AAPL_WORKBOOK,
    ProductionWorkbookProfile,
    SheetSectionProfile,
    production_workbook_available,
)


def build_profiled_custom_run_workbook(path: Path, *, ticker: str = "AAPL") -> Path:
    """
    Build a profile-driven test workbook.

    Sheet names are intentionally non-standard to prove the parser does not assume
    Bloomberg worksheet names.
    """
    workbook = Workbook()
    workbook.remove(workbook.active)

    metadata = workbook.create_sheet("TEST_meta_kv")
    metadata["A1"] = "Field"
    metadata["B1"] = "Value"
    metadata["A2"] = "Ticker"
    metadata["B2"] = ticker
    metadata["A3"] = "Company Name"
    metadata["B3"] = "Apple Inc."
    metadata["A4"] = "Currency"
    metadata["B4"] = "USD"
    metadata["A5"] = "Fiscal Year End"
    metadata["B5"] = "September"

    market = workbook.create_sheet("TEST_mkt_kv")
    market["A1"] = "Field"
    market["B1"] = "Value"
    market["A2"] = "Share Price"
    market["B2"] = 195.5
    market["A3"] = "Market Cap"
    market["B3"] = 3000000000000
    market["A4"] = "Shares Outstanding"
    market["B4"] = 15300000000

    historical = workbook.create_sheet("TEST_hist_ts")
    historical.append(["Metric", "FY2023", "FY2024"])
    historical.append(["Revenue", 383285000000, 391035000000])
    historical.append(["Net Income", 96995000000, 93736000000])
    historical.append(["Total Assets", 352755000000, 364980000000])

    proprietary = workbook.create_sheet("TEST_prop_ts")
    proprietary.append(["Metric", "FY2024"])
    proprietary.append(["ROIC", 0.45])
    proprietary.append(["FCF Yield", 0.035])

    valuation = workbook.create_sheet("TEST_val_ts")
    valuation.append(["Metric", "Current"])
    valuation.append(["P/E Ratio", 28.5])
    valuation.append(["EV/EBITDA", 22.1])

    quality = workbook.create_sheet("TEST_qual_mv")
    quality.append(["Metric", "Score"])
    quality.append(["Business Quality Score", 8.5])
    quality.append(["Management Quality", 9.0])

    assumptions = workbook.create_sheet("TEST_asm_kv")
    assumptions["A1"] = "Field"
    assumptions["B1"] = "Value"
    assumptions["A2"] = "Terminal Growth Rate"
    assumptions["B2"] = 0.03
    assumptions["A3"] = "WACC"
    assumptions["B3"] = 0.085

    workbook.save(path)
    workbook.close()
    return path


def build_test_profile() -> ProductionWorkbookProfile:
    return ProductionWorkbookProfile(
        version=1,
        evidence_tickers=("TEST",),
        sections=(
            SheetSectionProfile("metadata", "TEST_meta_kv", "key_value", data_start_row=2),
            SheetSectionProfile("market_data", "TEST_mkt_kv", "key_value", data_start_row=2),
            SheetSectionProfile(
                "historical_metrics",
                "TEST_hist_ts",
                "time_series",
                header_row=1,
                data_start_row=2,
            ),
            SheetSectionProfile(
                "proprietary_metrics",
                "TEST_prop_ts",
                "time_series",
                header_row=1,
                data_start_row=2,
            ),
            SheetSectionProfile(
                "valuation_metrics",
                "TEST_val_ts",
                "time_series",
                header_row=1,
                data_start_row=2,
            ),
            SheetSectionProfile(
                "quality_metrics",
                "TEST_qual_mv",
                "metric_value",
                data_start_row=2,
            ),
            SheetSectionProfile("assumptions", "TEST_asm_kv", "key_value", data_start_row=2),
        ),
    )


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
def test_custom_run_profile() -> ProductionWorkbookProfile:
    return build_test_profile()


@pytest.fixture
def sample_custom_run_workbook(fixtures_dir: Path, test_custom_run_profile) -> Path:
    path = fixtures_dir / "custom_run_filter.xlsx"
    build_profiled_custom_run_workbook(path, ticker="AAPL")
    profile_path = fixtures_dir / "custom_run_filter.profile.json"
    profile_path.write_text(
        json.dumps(test_custom_run_profile.to_dict(), indent=2),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def production_custom_run_workbook() -> Path:
    if not production_workbook_available():
        pytest.skip(
            "Production AAPL Custom_Run_Filter workbook not committed. "
            f"Add it at: {PRODUCTION_AAPL_WORKBOOK}"
        )
    return PRODUCTION_AAPL_WORKBOOK


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
