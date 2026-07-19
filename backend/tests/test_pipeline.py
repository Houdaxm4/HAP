"""Integration tests for HAP v1 ingestion pipeline through AnalysisEngine.run()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from models.analysis import Analysis, AnalysisFiles, UploadedFileMetadata
from pipeline.orchestrator import PipelineOrchestrator
from services.analysis_service import AnalysisService
from services.file_service import FileService
from services.output_service import OutputService


@pytest.fixture
def pipeline_env(tmp_path: Path, sample_workbook: Path, sample_custom_run_workbook: Path):
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
                filename="custom_run_filter.xlsx",
                stored_filename="custom_run_filter.xlsx",
                size_bytes=sample_custom_run_workbook.stat().st_size,
                uploaded_at="2026-07-08T00:00:00+00:00",
            ),
        ),
    )
    analysis_service.save(analysis)

    upload_dir = file_service.analysis_upload_dir(analysis.analysis_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "prefilled_workbook.xlsx").write_bytes(sample_workbook.read_bytes())
    (upload_dir / "custom_run_filter.xlsx").write_bytes(sample_custom_run_workbook.read_bytes())

    orchestrator = PipelineOrchestrator(
        analysis_service=analysis_service,
        file_service=file_service,
        output_service=output_service,
    )
    return orchestrator, analysis_service, output_service


def test_aapl_pipeline_reaches_analysis_engine(
    pipeline_env,
    mock_company_facts,
    mock_filings_manifest,
):
    orchestrator, analysis_service, output_service = pipeline_env

    with patch.object(
        orchestrator.fetch_sec_stage.sec_service,
        "resolve_cik",
        return_value="0000320193",
    ), patch.object(
        orchestrator.fetch_sec_stage.sec_service,
        "fetch_filings_manifest",
        return_value=mock_filings_manifest,
    ), patch.object(
        orchestrator.fetch_sec_stage.sec_service,
        "fetch_company_facts",
        return_value=mock_company_facts,
    ):
        result = orchestrator.run("test-analysis")

    assert result.pipeline.state == "complete"
    assert result.pipeline.outputs.custom_run_data is not None
    assert result.pipeline.outputs.company_financial_model is not None
    assert result.pipeline.outputs.analysis_engine_result is not None
    assert result.is_pipeline_complete

    engine_result = output_service.read_json("test-analysis", "analysis_engine_result.json")
    assert engine_result["status"] == "accepted"
    assert engine_result["ticker"] == "AAPL"

    custom_run = output_service.read_json("test-analysis", "custom_run_data.json")
    assert custom_run["metadata"]["Ticker"] == "AAPL"
    assert len(custom_run["historical_metrics"]) >= 1

    completed_path = output_service.artifact_path("test-analysis", "completed_workbook.xlsx")
    assert completed_path.exists()

    reloaded = analysis_service.get("test-analysis")
    assert any(entry.action == "run_analysis" for entry in reloaded.decision_log)
