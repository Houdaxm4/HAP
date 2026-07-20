"""Tests for the Sprint 5 validation harness (no analytical logic changes)."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from models.analysis import Analysis
from models.pipeline import PipelineOutputs, PipelineStatus
from validation.discovery import discover_cases
from validation.extract import extract_analytical_fields, module_coverage
from validation.report import CSV_COLUMNS, write_reports
from validation.runner import ValidationBatchResult, ValidationRow, run_validation


def _make_case_dir(
    root: Path,
    name: str,
    *,
    workbook: bool = True,
    custom_run: bool = True,
    manifest: dict | None = None,
) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True)
    if workbook:
        (case_dir / "workbook.xlsx").write_bytes(b"fake-xlsx")
    if custom_run:
        (case_dir / "custom_run_filter.csv").write_text("worksheet,cell\n", encoding="utf-8")
    if manifest is not None:
        import json

        (case_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return case_dir


def test_discover_cases_reads_manifest_and_skips_incomplete(tmp_path: Path):
    input_dir = tmp_path / "companies"
    input_dir.mkdir()
    _make_case_dir(
        input_dir,
        "aapl",
        manifest={"company": "Apple Inc.", "ticker": "AAPL"},
    )
    _make_case_dir(input_dir, "incomplete", custom_run=False)

    cases = discover_cases(input_dir)
    assert len(cases) == 1
    assert cases[0].company == "Apple Inc."
    assert cases[0].ticker == "AAPL"
    assert cases[0].workbook_path.name == "workbook.xlsx"


def test_extract_analytical_fields_from_engine_result():
    engine = {
        "business_quality": {"score": 72.5, "classification_label": "Good"},
        "investment_attractiveness": {"score": 61.0, "classification_label": "Attractive"},
        "recommendation": {"recommendation_label": "Buy", "recommendation": "BUY"},
        "metrics": [
            {"code": "FAIR_VALUE_BASE", "value": 150.0},
            {"code": "SHARE_PRICE", "value": 120.0},
            {"code": "MARGIN_OF_SAFETY", "value": 0.2},
            {"code": "EXPECTED_CAGR", "value": 0.12},
        ],
        "modules": [],
    }
    fields = extract_analytical_fields(engine)
    assert fields["business_quality_score"] == 72.5
    assert fields["recommendation"] == "Buy"
    assert fields["fair_value"] == 150.0
    assert fields["expected_return"] == 0.12


def test_module_coverage_flags_incomplete():
    engine = {
        "modules": [
            {"module_name": "profitability", "status": "ok"},
            {"module_name": "margins", "status": "skipped"},
            {"module_name": "growth", "status": "error"},
        ]
    }
    ok, skipped, errors, incomplete = module_coverage(engine)
    assert ok == 1
    assert skipped == 1
    assert errors == 1
    assert incomplete == ["margins", "growth"]


def test_run_validation_continues_after_failure(tmp_path: Path):
    input_dir = tmp_path / "companies"
    input_dir.mkdir()
    _make_case_dir(input_dir, "ok_co", manifest={"company": "Ok Co", "ticker": "OK"})
    _make_case_dir(input_dir, "bad_co", manifest={"company": "Bad Co", "ticker": "BAD"})
    output_dir = tmp_path / "out"

    analysis_service = MagicMock()
    file_service = MagicMock()
    output_service = MagicMock()
    orchestrator = MagicMock()

    created = {
        "OK": Analysis(
            analysis_id="id-ok",
            company="Ok Co",
            ticker="OK",
            analysis_type="Validation",
            status="created",
        ),
        "BAD": Analysis(
            analysis_id="id-bad",
            company="Bad Co",
            ticker="BAD",
            analysis_type="Validation",
            status="created",
        ),
    }

    def create_side_effect(request):
        return created[request.ticker]

    analysis_service.create.side_effect = create_side_effect
    def _upload_dir(aid: str) -> Path:
        path = tmp_path / "uploads" / aid
        path.mkdir(parents=True, exist_ok=True)
        return path

    file_service.analysis_upload_dir.side_effect = _upload_dir

    ok_result = Analysis(
        analysis_id="id-ok",
        company="Ok Co",
        ticker="OK",
        analysis_type="Validation",
        status="complete",
        pipeline=PipelineStatus(
            state="complete",
            progress_pct=100,
            outputs=PipelineOutputs(
                completed_workbook="outputs/id-ok/completed_workbook.xlsx",
                provenance_report="outputs/id-ok/provenance_report.json",
                validation_report="outputs/id-ok/validation_report.json",
                company_financial_model="outputs/id-ok/company_financial_model.json",
                analysis_engine_result="outputs/id-ok/analysis_engine_result.json",
            ),
        ),
    )
    bad_result = Analysis(
        analysis_id="id-bad",
        company="Bad Co",
        ticker="BAD",
        analysis_type="Validation",
        status="failed",
        pipeline=PipelineStatus(state="failed", error="SEC lookup failed", progress_pct=0),
    )

    def run_side_effect(analysis_id: str):
        if analysis_id == "id-ok":
            return ok_result
        return bad_result

    orchestrator.run.side_effect = run_side_effect
    output_service.artifact_path.return_value = tmp_path / "engine.json"
    (tmp_path / "engine.json").write_text("{}", encoding="utf-8")
    output_service.read_json.return_value = {
        "business_quality": {"score": 80, "classification_label": "Excellent"},
        "investment_attractiveness": {"score": 70, "classification_label": "Attractive"},
        "recommendation": {"recommendation_label": "Buy"},
        "metrics": [
            {"code": "FAIR_VALUE_BASE", "value": 100},
            {"code": "SHARE_PRICE", "value": 90},
            {"code": "MARGIN_OF_SAFETY", "value": 0.1},
            {"code": "EXPECTED_CAGR", "value": 0.15},
        ],
        "modules": [{"module_name": "profitability", "status": "ok"}],
    }

    batch = run_validation(
        input_dir,
        output_dir,
        analysis_service=analysis_service,
        file_service=file_service,
        output_service=output_service,
        orchestrator=orchestrator,
    )

    assert len(batch.rows) == 2
    by_ticker = {row.ticker: row for row in batch.rows}
    assert by_ticker["OK"].status == "success"
    assert by_ticker["BAD"].status == "failed"
    assert "SEC lookup failed" in by_ticker["BAD"].failure_reason
    assert (output_dir / "validation_failures.log").exists()
    assert orchestrator.run.call_count == 2


def test_write_reports_csv_and_summary(tmp_path: Path):
    rows = [
        ValidationRow(
            company="Ok Co",
            ticker="OK",
            business_quality_score=80,
            business_quality_rating="Excellent",
            investment_attractiveness_score=70,
            investment_attractiveness_rating="Attractive",
            recommendation="Buy",
            fair_value=100,
            current_price=90,
            margin_of_safety=0.1,
            expected_return=0.15,
            analysis_duration_sec=12.5,
            status="success",
        ),
        ValidationRow(
            company="Bad Co",
            ticker="BAD",
            analysis_duration_sec=3.0,
            status="failed",
            failure_reason="boom",
            missing_data=True,
            incomplete_module_coverage=True,
            incomplete_modules=["margins"],
        ),
    ]
    batch = ValidationBatchResult(rows=rows, input_dir=tmp_path, output_dir=tmp_path / "out")
    csv_path, md_path = write_reports(batch)

    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == CSV_COLUMNS
        data = list(reader)
    assert len(data) == 2
    assert data[0]["Ticker"] == "OK"
    assert data[1]["Failure Reason"] == "boom"

    summary = md_path.read_text(encoding="utf-8")
    assert "Total companies:** 2" in summary
    assert "Successful analyses:** 1" in summary
    assert "Failed analyses:** 1" in summary
    assert "Average runtime:** 7.75s" in summary
    assert "Companies missing data:** 1" in summary
    assert "incomplete module coverage:** 1" in summary
