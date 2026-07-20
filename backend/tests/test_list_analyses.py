"""Tests for GET /analyses summary DTOs."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app, analysis_service, output_service
from models.analysis import CreateAnalysisRequest
from models.pipeline import PipelineOutputs, PipelineStage, PipelineStatus


client = TestClient(app)


def test_list_analyses_returns_empty_initially(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(analysis_service, "storage_dir", tmp_path / "analyses")
    analysis_service.storage_dir.mkdir(parents=True, exist_ok=True)

    response = client.get("/analyses")
    assert response.status_code == 200
    assert response.json() == []


def test_list_analyses_projects_engine_fields_without_invented_aliases(
    tmp_path: Path,
    monkeypatch,
):
    analyses_dir = tmp_path / "analyses"
    outputs_dir = tmp_path / "outputs"
    analyses_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(analysis_service, "storage_dir", analyses_dir)
    monkeypatch.setattr(output_service, "outputs_dir", outputs_dir)

    created = analysis_service.create(
        CreateAnalysisRequest(company="Apple Inc.", ticker="AAPL", analysis_type="new_company")
    )
    created.pipeline = PipelineStatus(
        state="complete",
        current_stage=PipelineStage.COMPLETE,
        progress_pct=100,
        outputs=PipelineOutputs(
            completed_workbook=f"outputs/{created.analysis_id}/completed_workbook.xlsx",
            provenance_report=f"outputs/{created.analysis_id}/provenance_report.json",
            validation_report=f"outputs/{created.analysis_id}/validation_report.json",
            company_financial_model=f"outputs/{created.analysis_id}/company_financial_model.json",
            analysis_engine_result=f"outputs/{created.analysis_id}/analysis_engine_result.json",
        ),
    )
    created.status = "complete"
    analysis_service.save(created)

    output_service.write_json(
        created.analysis_id,
        "analysis_engine_result.json",
        {
            "analysis_id": created.analysis_id,
            "ticker": "AAPL",
            "modules": [],
            "business_quality": {
                "score": 88.5,
                "confidence": 0.8,
                "classification": "EXCELLENT_BUSINESS",
                "classification_label": "Excellent Business",
            },
            "investment_attractiveness": {
                "score": 72.0,
                "confidence": 0.7,
                "classification": "FAIRLY_VALUED",
                "classification_label": "Fairly Valued",
            },
            "recommendation": {
                "recommendation": "BUY",
                "recommendation_label": "Buy",
                "business_quality_classification": "EXCELLENT_BUSINESS",
                "investment_attractiveness_classification": "FAIRLY_VALUED",
            },
        },
    )

    response = client.get("/analyses")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    row = payload[0]
    assert row["ticker"] == "AAPL"
    assert row["recommendation"] == "BUY"
    assert row["recommendation_label"] == "Buy"
    assert row["business_quality_score"] == 88.5
    assert row["investment_attractiveness_score"] == 72.0
    assert row["is_complete"] is True
    assert "overall_score" not in row
    assert "display_status" not in row

    detail = client.get(f"/analysis/{created.analysis_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["has_engine_result"] is True
    assert body["business_quality_score"] == 88.5
