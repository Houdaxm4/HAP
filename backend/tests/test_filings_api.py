"""API tests for the Filing Collector endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models.filings import CollectFilingsRequest, FilingCollectionResult, FilingDocumentMeta
from services.filing_collector import FilingCollector
from services.filing_db import FilingDatabase


@pytest.fixture
def filings_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = FilingDatabase(db_path=tmp_path / "hap.db")
    collector = FilingCollector(database=db, cache_dir=tmp_path / "filings", request_delay_seconds=0)

    def fake_collect(request: CollectFilingsRequest) -> FilingCollectionResult:
        latest_10k = FilingDocumentMeta(
            accession_number="0000320193-24-000200",
            form="10-K/A",
            base_form="10-K",
            is_amendment=True,
            filing_date="2024-12-01",
            report_date="2024-09-28",
            selected_role="latest_10k",
            html_path=str(tmp_path / "k.htm"),
            xbrl_path=str(tmp_path / "k.xml"),
        )
        latest_10q = FilingDocumentMeta(
            accession_number="0000320193-25-000010",
            form="10-Q",
            base_form="10-Q",
            filing_date="2025-01-31",
            report_date="2024-12-28",
            selected_role="latest_10q",
        )
        historical = FilingDocumentMeta(
            accession_number="0000320193-23-000100",
            form="10-K",
            base_form="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            selected_role="historical_10k",
        )
        result = FilingCollectionResult(
            collection_id="col-1",
            ticker=request.ticker.upper(),
            cik="0000320193",
            company_name="Apple Inc.",
            status="completed",
            latest_10k=latest_10k,
            latest_10q=latest_10q,
            historical_10ks=[historical],
            filings=[latest_10k, latest_10q, historical],
            cache_dir=str(tmp_path / "filings" / "0000320193"),
        )
        collector.database.save_collection(result, historical_years=request.historical_years)
        return result

    monkeypatch.setattr(collector, "collect", fake_collect)
    monkeypatch.setattr("main.filing_collector", collector)
    return TestClient(app), collector


def test_filings_collect_and_get_endpoints(filings_client):
    client, _collector = filings_client
    response = client.post(
        "/filings/collect",
        json={"ticker": "AAPL", "historical_years": 10, "download_documents": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["latest_10k"]["form"] == "10-K/A"
    assert payload["latest_10q"]["form"] == "10-Q"
    assert len(payload["historical_10ks"]) == 1
    assert "No extraction performed" in payload["message"]

    by_ticker = client.get("/filings/AAPL")
    assert by_ticker.status_code == 200
    assert by_ticker.json()["collection_id"] == payload["collection_id"]

    by_id = client.get(f"/filings/collection/{payload['collection_id']}")
    assert by_id.status_code == 200
