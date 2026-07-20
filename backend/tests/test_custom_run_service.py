"""Unit tests for Bloomberg Custom_Run_Filter parsing and validation."""

from __future__ import annotations

from services.custom_run_service import CustomRunParseError, CustomRunService
from services.custom_run_validation import CustomRunValidationService
import pytest


def test_parse_bloomberg_custom_run(sample_custom_run_xlsx):
    data = CustomRunService().parse(sample_custom_run_xlsx, "Custom_Run_Filter_AAPL.xlsx")
    assert data.ticker == "AAPL"
    assert data.company == "Apple Inc."
    assert data.ticker_sheet_name == "AAPL"
    assert data.summary_field_count >= 50
    assert data.period_count >= 20
    assert data.series_count >= 10
    assert data.scalar("Current PE10") == 28.5
    assert data.market_data.get("Current Price (Live Price)") == 190.0
    assert "WACC" in data.assumptions or data.scalar("WACC") == 0.09


def test_reject_csv_mapping_file(sample_workbook, tmp_path):
    csv_path = tmp_path / "custom_run_filter.csv"
    csv_path.write_text(
        "worksheet,cell,concept,period\nIncome Statement,B5,Revenue,FY2024\n",
        encoding="utf-8",
    )
    with pytest.raises(CustomRunParseError, match="Bloomberg-derived Excel"):
        CustomRunService().parse(csv_path, "custom_run_filter.csv")


def test_validate_bloomberg_custom_run(sample_custom_run_xlsx):
    data = CustomRunService().parse(sample_custom_run_xlsx, "Custom_Run_Filter_AAPL.xlsx")
    report = CustomRunValidationService().validate("test-analysis", data)
    assert report.fail_count == 0
    assert report.pass_count > 0
