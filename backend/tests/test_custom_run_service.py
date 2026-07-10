"""Unit tests for custom_run parsing and validation reports."""

from __future__ import annotations

from pathlib import Path

from models.workbook_schema import WorkbookStructure
from services.custom_run_service import CustomRunParseError, CustomRunService


def test_parse_custom_run_csv(sample_custom_run_csv):
    mapping = CustomRunService().parse(sample_custom_run_csv, "custom_run_filter.csv")
    assert mapping.entry_count == 3
    assert mapping.entries[0].worksheet == "Income Statement"
    assert mapping.entries[0].cell == "B5"
    assert mapping.entries[0].concept == "Revenue"
    assert mapping.entries[0].period == "FY2024"
    assert mapping.entries[0].xbrl_tag == "Revenues"


def test_parse_period_formats():
    service = CustomRunService
    assert service.parse_period("FY2024") == {"fiscal_year": 2024, "is_annual": True}
    assert service.parse_period("FY24") == {"fiscal_year": 2024, "is_annual": True}
    assert service.parse_period("Q1 2024") == {
        "fiscal_year": 2024,
        "fiscal_quarter": 1,
        "is_annual": False,
    }
    assert service.parse_period("2024-Q3") == {
        "fiscal_year": 2024,
        "fiscal_quarter": 3,
        "is_annual": False,
    }
    assert service.parse_period("latest_annual") == {
        "alias": "latest_annual",
        "is_annual": True,
    }
    assert service.parse_period("not-a-period") is None


def test_validation_report_passes_for_clean_filter(tmp_path: Path):
    path = tmp_path / "custom_run_filter.csv"
    path.write_text(
        "worksheet,cell,concept,period,ticker,value,unit\n"
        "Income Statement,B5,Revenue,FY2024,AAPL,100,USD\n"
        "Income Statement,C5,Revenue,Q1 2024,AAPL,20,USD\n"
        "Income Statement,D5,Revenue,Q2 2024,AAPL,30,USD\n"
        "Income Statement,E5,Revenue,Q3 2024,AAPL,25,USD\n"
        "Income Statement,F5,Revenue,Q4 2024,AAPL,25,USD\n",
        encoding="utf-8",
    )
    service = CustomRunService()
    mapping = service.parse(path, "custom_run_filter.csv")
    structure = WorkbookStructure(
        workbook_filename="wb.xlsx",
        worksheet_names=["Income Statement"],
        visible_sheets=["Income Statement"],
    )
    report = service.validate(
        mapping,
        analysis_id="a1",
        ticker="AAPL",
        structure=structure,
    )
    assert report.is_valid
    assert report.fail_count == 0
    assert any(check.check_type == "required_columns" and check.status == "pass" for check in report.checks)
    assert any(check.check_type == "ticker" and check.status == "pass" for check in report.checks)
    assert any(check.check_type == "fiscal_dates" and check.status == "pass" for check in report.checks)
    assert "Template was not populated" in report.summary


def test_validation_detects_ticker_mismatch_duplicates_missing_quarters(tmp_path: Path):
    path = tmp_path / "bad_filter.csv"
    path.write_text(
        "worksheet,cell,concept,period,ticker,value\n"
        "Income Statement,B5,Revenue,Q1 2024,MSFT,10\n"
        "Income Statement,C5,Revenue,Q1 2024,MSFT,11\n"
        "Income Statement,D5,Revenue,Q3 2024,MSFT,12\n",
        encoding="utf-8",
    )
    service = CustomRunService()
    mapping = service.parse(path, "bad_filter.csv")
    report = service.validate(mapping, analysis_id="a1", ticker="AAPL", structure=None)

    assert report.is_valid is False
    assert any(check.check_type == "ticker" and check.status == "fail" for check in report.checks)
    assert any(check.check_type == "duplicate_periods" and check.status == "fail" for check in report.checks)
    assert any(check.check_type == "missing_quarters" and check.status == "warn" for check in report.checks)


def test_validation_numeric_inconsistency(tmp_path: Path):
    path = tmp_path / "numeric.csv"
    path.write_text(
        "worksheet,cell,concept,period,value\n"
        "Income Statement,B5,Revenue,FY2024,100\n"
        "Income Statement,C5,Revenue,Q1 2024,10\n"
        "Income Statement,D5,Revenue,Q2 2024,10\n"
        "Income Statement,E5,Revenue,Q3 2024,10\n"
        "Income Statement,F5,Revenue,Q4 2024,10\n",
        encoding="utf-8",
    )
    service = CustomRunService()
    mapping = service.parse(path, "numeric.csv")
    report = service.validate(mapping, analysis_id="a1", ticker="AAPL")
    assert report.is_valid
    assert any(
        check.check_type == "numeric_consistency" and check.status == "warn"
        for check in report.checks
    )


def test_invalid_numeric_value_raises(tmp_path: Path):
    path = tmp_path / "bad_value.csv"
    path.write_text(
        "worksheet,cell,concept,period,value\n"
        "Income Statement,B5,Revenue,FY2024,not-a-number\n",
        encoding="utf-8",
    )
    try:
        CustomRunService().parse(path, "bad_value.csv")
        assert False, "Expected CustomRunParseError"
    except CustomRunParseError as exc:
        assert "numeric" in str(exc).lower()
