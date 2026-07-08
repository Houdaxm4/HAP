"""Shared pytest fixtures for HAP backend pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


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
  balance["A5"] = "Total Assets"
  balance["B5"] = None

  path = fixtures_dir / "prefilled_workbook.xlsx"
  workbook.save(path)
  workbook.close()
  return path


@pytest.fixture
def sample_custom_run_csv(fixtures_dir: Path) -> Path:
  content = """worksheet,cell,concept,period,xbrl_tag
Income Statement,B5,Revenue,FY2024,Revenues
Income Statement,B6,Net Income,FY2024,NetIncomeLoss
Balance Sheet,B5,Total Assets,FY2024,Assets
"""
  path = fixtures_dir / "custom_run_filter.csv"
  path.write_text(content, encoding="utf-8")
  return path


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
