"""API tests for analysis list and infrastructure upload validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from pipeline.orchestrator import PipelineOrchestrator
from services.analysis_service import AnalysisService
from services.file_service import FileService
from services.output_service import OutputService


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    analyses_dir = tmp_path / "analyses"
    uploads_dir = tmp_path / "uploads"
    outputs_dir = tmp_path / "outputs"

    test_analysis_service = AnalysisService(storage_dir=analyses_dir)
    test_file_service = FileService(uploads_dir=uploads_dir)
    test_output_service = OutputService(outputs_dir=outputs_dir)
    test_orchestrator = PipelineOrchestrator(
        analysis_service=test_analysis_service,
        file_service=test_file_service,
        output_service=test_output_service,
    )

    monkeypatch.setattr("main.analysis_service", test_analysis_service)
    monkeypatch.setattr("main.file_service", test_file_service)
    monkeypatch.setattr("main.output_service", test_output_service)
    monkeypatch.setattr("main.pipeline_orchestrator", test_orchestrator)

    return TestClient(app)


def test_create_upload_runs_infrastructure_pipeline(
    client: TestClient,
    sample_workbook: Path,
    sample_custom_run_csv: Path,
):
    create_response = client.post(
        "/analysis/create",
        json={
            "company": "Apple Inc.",
            "ticker": "AAPL",
            "analysis_type": "Annual Update",
        },
    )
    assert create_response.status_code == 200
    analysis_id = create_response.json()["analysis_id"]

    with sample_workbook.open("rb") as workbook_handle, sample_custom_run_csv.open("rb") as filter_handle:
        upload_response = client.post(
            f"/analysis/{analysis_id}/upload",
            files={
                "prefilled_workbook": (
                    "prefilled_workbook.xlsx",
                    workbook_handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "custom_run_filter": (
                    "custom_run_filter.csv",
                    filter_handle,
                    "text/csv",
                ),
            },
        )

    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    assert upload_payload["pipeline_started"] is True

    # TestClient runs background tasks inline before returning.
    get_response = client.get(f"/analysis/{analysis_id}")
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["display_status"] == "Waiting for filing collection"
    assert payload["pipeline"]["state"] == "waiting"
    assert payload["pipeline"]["current_stage"] == "waiting_for_filing_collection"
    assert "workbook_uploaded" in payload["pipeline"]["stages_completed"]
    assert "workbook_parsed" in payload["pipeline"]["stages_completed"]
    assert "custom_run_filter_uploaded" in payload["pipeline"]["stages_completed"]
    assert "custom_run_filter_validated" in payload["pipeline"]["stages_completed"]
    assert payload["pipeline"]["outputs"]["custom_run_validation_report"] is not None

    validation = client.get(f"/analysis/{analysis_id}/custom-run-validation")
    assert validation.status_code == 200
    report = validation.json()
    assert report["is_valid"] is True
    assert "Template was not populated" in report["summary"]

    list_response = client.get("/analysis")
    assert list_response.status_code == 200
    assert any(item["analysis_id"] == analysis_id for item in list_response.json())


def test_upload_rejects_missing_custom_run(
    client: TestClient,
    sample_workbook: Path,
):
    create_response = client.post(
        "/analysis/create",
        json={"company": "Apple Inc.", "ticker": "AAPL", "analysis_type": "New Company"},
    )
    analysis_id = create_response.json()["analysis_id"]

    with sample_workbook.open("rb") as workbook_handle:
        upload_response = client.post(
            f"/analysis/{analysis_id}/upload",
            files={
                "prefilled_workbook": (
                    "prefilled_workbook.xlsx",
                    workbook_handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

    assert upload_response.status_code == 422
