"""Unit tests for profile-driven Bloomberg Custom_Run_Filter parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.custom_run_parser import CustomRunParseError, CustomRunParser
from ingestion.custom_run_validator import CustomRunValidator


def test_parse_profiled_workbook(sample_custom_run_workbook, test_custom_run_profile):
    data = CustomRunParser(profile=test_custom_run_profile).parse(
        sample_custom_run_workbook,
        "custom_run_filter.xlsx",
    )
    assert data.ticker == "AAPL"
    assert "TEST_meta_kv" in data.worksheets_found
    assert data.market_data["Share Price"] == 195.5
    assert len(data.historical_metrics) == 3


def test_reject_mapping_csv(tmp_path: Path):
    csv_path = tmp_path / "custom_run_filter.csv"
    csv_path.write_text("worksheet,cell,concept,period\nIncome Statement,B5,Revenue,FY2024\n")
    with pytest.raises(CustomRunParseError, match="Bloomberg-derived Excel workbook"):
        CustomRunParser().parse(csv_path, "custom_run_filter.csv")


def test_reject_workbook_without_production_profile(sample_custom_run_workbook):
    with pytest.raises(CustomRunParseError, match="verified production Custom_Run_Filter profile"):
        CustomRunParser().parse(sample_custom_run_workbook, "custom_run_filter.xlsx")


def test_validate_profiled_workbook(sample_custom_run_workbook, test_custom_run_profile):
    data = CustomRunParser(profile=test_custom_run_profile).parse(
        sample_custom_run_workbook,
        "custom_run_filter.xlsx",
    )
    report = CustomRunValidator().validate(data, expected_ticker="AAPL")
    assert report.is_valid
    assert report.ticker == "AAPL"
