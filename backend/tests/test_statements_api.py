"""API tests for financial statement extraction endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from models.analysis import CreateAnalysisRequest
from models.statements import (
    ExtractStatementsRequest,
    FinancialStatement,
    FinancialStatementsResult,
)
from services.analysis_service import AnalysisService
from services.output_service import OutputService
from services.statement_extractor import FinancialStatementExtractor


@pytest.fixture
def statements_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    analysis_service = AnalysisService(storage_dir=tmp_path / "analyses")
    output_service = OutputService(outputs_dir=tmp_path / "outputs")

    def fake_extract(request: ExtractStatementsRequest) -> FinancialStatementsResult:
        def stmt(statement_type: str, title: str, count: int) -> FinancialStatement:
            return FinancialStatement(
                statement_type=statement_type,  # type: ignore[arg-type]
                title=title,
                line_item_count=count,
                populated_value_count=count,
            )

        return FinancialStatementsResult(
            extraction_id="ext-1",
            ticker=request.ticker.upper(),
            cik="0000320193",
            company_name="Apple Inc.",
            balance_sheet=stmt("balance_sheet", "Balance Sheet", 3),
            income_statement=stmt("income_statement", "Income Statement", 5),
            cash_flow=stmt("cash_flow", "Cash Flow Statement", 4),
            annual_periods=["FY2023", "FY2024"],
        )

    extractor = FinancialStatementExtractor()
    monkeypatch.setattr(extractor, "extract", fake_extract)
    monkeypatch.setattr("main.statement_extractor", extractor)
    monkeypatch.setattr("main.analysis_service", analysis_service)
    monkeypatch.setattr("main.output_service", output_service)
    return TestClient(app), analysis_service


def test_extract_statements_endpoint(statements_client):
    client, _analysis_service = statements_client
    response = client.post(
        "/statements/extract",
        json={"ticker": "AAPL", "max_annual_periods": 10, "include_quarters": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["balance_sheet"]["statement_type"] == "balance_sheet"
    assert payload["income_statement"]["statement_type"] == "income_statement"
    assert payload["cash_flow"]["statement_type"] == "cash_flow"
    assert "No ratios or analysis" in payload["message"]
    assert "ratios" not in payload


def test_extract_statements_for_analysis(statements_client):
    client, analysis_service = statements_client
    analysis = analysis_service.create(
        CreateAnalysisRequest(company="Apple Inc.", ticker="AAPL", analysis_type="Annual Update")
    )

    response = client.post(f"/analysis/{analysis.analysis_id}/extract-statements")
    assert response.status_code == 200
    payload = response.json()
    assert payload["extraction_id"] == "ext-1"

    stored = analysis_service.get(analysis.analysis_id)
    assert stored.financial_statements_id == "ext-1"
    assert stored.status == "statements_extracted"
    assert stored.pipeline.outputs.financial_statements is not None

    get_response = client.get(f"/analysis/{analysis.analysis_id}/statements")
    assert get_response.status_code == 200
    assert get_response.json()["cash_flow"]["title"] == "Cash Flow Statement"
