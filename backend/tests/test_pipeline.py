"""Integration tests for the HAP infrastructure pipeline (pre-SEC)."""

from __future__ import annotations

from pathlib import Path

import pytest

from models.analysis import Analysis, AnalysisFiles, UploadedFileMetadata
from models.pipeline import PipelineStage
from pipeline.orchestrator import PipelineOrchestrator
from services.analysis_service import AnalysisService
from services.file_service import FileService
from services.output_service import OutputService


@pytest.fixture
def pipeline_env(tmp_path: Path, sample_workbook: Path, sample_custom_run_csv: Path):
    analysis_service = AnalysisService(storage_dir=tmp_path / "analyses")
    file_service = FileService(uploads_dir=tmp_path / "uploads")
    output_service = OutputService(outputs_dir=tmp_path / "outputs")

    analysis = Analysis(
        analysis_id="test-analysis",
        company="Apple Inc.",
        ticker="AAPL",
        analysis_type="Annual Update",
        status="uploaded",
        files=AnalysisFiles(
            prefilled_workbook=UploadedFileMetadata(
                filename="prefilled_workbook.xlsx",
                stored_filename="prefilled_workbook.xlsx",
                size_bytes=sample_workbook.stat().st_size,
                uploaded_at="2026-07-08T00:00:00+00:00",
            ),
            custom_run_filter=UploadedFileMetadata(
                filename="custom_run_filter.csv",
                stored_filename="custom_run_filter.csv",
                size_bytes=sample_custom_run_csv.stat().st_size,
                uploaded_at="2026-07-08T00:00:00+00:00",
            ),
        ),
    )
    analysis_service.save(analysis)

    upload_dir = file_service.analysis_upload_dir(analysis.analysis_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "prefilled_workbook.xlsx").write_bytes(sample_workbook.read_bytes())
    (upload_dir / "custom_run_filter.csv").write_bytes(sample_custom_run_csv.read_bytes())

    orchestrator = PipelineOrchestrator(
        analysis_service=analysis_service,
        file_service=file_service,
        output_service=output_service,
    )
    return orchestrator, analysis_service, output_service


def test_infrastructure_pipeline_stops_at_filing_collection(pipeline_env):
    orchestrator, analysis_service, output_service = pipeline_env

    result = orchestrator.run("test-analysis")

    assert result.pipeline.state == "waiting"
    assert result.pipeline.current_stage == PipelineStage.WAITING_FOR_FILING_COLLECTION
    assert result.pipeline.progress_pct == 100
    assert result.is_pipeline_complete
    assert result.status == "waiting_for_filing_collection"

    expected_stages = [
        PipelineStage.WORKBOOK_UPLOADED,
        PipelineStage.WORKBOOK_PARSED,
        PipelineStage.CUSTOM_RUN_FILTER_UPLOADED,
        PipelineStage.CUSTOM_RUN_FILTER_VALIDATED,
        PipelineStage.WAITING_FOR_FILING_COLLECTION,
    ]
    assert result.pipeline.stages_completed == expected_stages

    assert result.pipeline.outputs.workbook_structure is not None
    assert result.pipeline.outputs.custom_run_mapping is not None
    assert result.pipeline.outputs.custom_run_validation_report is not None
    # SEC / fill outputs must not be produced in this milestone.
    assert result.pipeline.outputs.sec_filings_manifest is None
    assert result.pipeline.outputs.completed_workbook is None

    structure = output_service.read_json("test-analysis", "workbook_structure.json")
    assert "Income Statement" in structure["worksheet_names"]

    mapping = output_service.read_json("test-analysis", "custom_run_mapping.json")
    assert mapping["entry_count"] == 3

    report = output_service.read_json("test-analysis", "custom_run_validation_report.json")
    assert report["is_valid"] is True
    assert report["fail_count"] == 0
    assert "Template was not populated" in report["summary"]

    assert any(entry.action == "waiting_for_filing_collection" for entry in result.decision_log)

    reloaded = analysis_service.get("test-analysis")
    assert reloaded.is_pipeline_complete


def test_pipeline_fails_on_invalid_custom_run_worksheet(pipeline_env):
    orchestrator, analysis_service, _output_service = pipeline_env
    custom_run_path = (
        orchestrator.file_service.analysis_upload_dir("test-analysis") / "custom_run_filter.csv"
    )
    custom_run_path.write_text(
        "worksheet,cell,concept,period\nMissing Sheet,B5,Revenue,FY2024\n",
        encoding="utf-8",
    )

    result = orchestrator.run("test-analysis")
    assert result.pipeline.state == "failed"
    assert result.status == "failed"
    assert "missing from the workbook" in (result.pipeline.error or "")
    reloaded = analysis_service.get("test-analysis")
    assert reloaded.pipeline.state == "failed"
