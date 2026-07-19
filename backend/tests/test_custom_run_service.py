"""Unit tests for Bloomberg Custom_Run_Filter parser."""

from __future__ import annotations

import pytest

from ingestion.custom_run_parser import CustomRunParseError, CustomRunParser
from ingestion.custom_run_validator import CustomRunValidator


def test_parse_bloomberg_custom_run_workbook(sample_custom_run_workbook):
    data = CustomRunParser().parse(sample_custom_run_workbook, "custom_run_filter.xlsx")
    assert data.ticker == "AAPL"
    assert data.company_name == "Apple Inc."
    assert len(data.historical_metrics) == 3
    assert len(data.proprietary_metrics) == 2
    assert data.market_data["Share Price"] == 195.5


def test_reject_mapping_csv(tmp_path):
    csv_path = tmp_path / "custom_run_filter.csv"
    csv_path.write_text("worksheet,cell,concept,period\nIncome Statement,B5,Revenue,FY2024\n")
    with pytest.raises(CustomRunParseError, match="Bloomberg-derived Excel workbook"):
        CustomRunParser().parse(csv_path, "custom_run_filter.csv")


def test_validate_custom_run_data(sample_custom_run_workbook):
    data = CustomRunParser().parse(sample_custom_run_workbook, "custom_run_filter.xlsx")
    report = CustomRunValidator().validate(data, expected_ticker="AAPL")
    assert report.is_valid
    assert report.fail_count == 0
