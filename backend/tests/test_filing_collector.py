"""Tests for the Filing Collector service (SEC EDGAR, cache, SQLite)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from models.filings import CollectFilingsRequest, FilingDocumentMeta
from services.filing_collector import FilingCollector, FilingCollectorError
from services.filing_db import FilingDatabase


def _submissions_payload() -> dict:
    return {
        "name": "Apple Inc.",
        "cik": "0000320193",
        "filings": {
            "recent": {
                "form": ["10-K", "10-K/A", "10-Q", "10-K", "8-K"],
                "accessionNumber": [
                    "0000320193-24-000123",
                    "0000320193-24-000200",
                    "0000320193-25-000010",
                    "0000320193-23-000100",
                    "0000320193-25-000011",
                ],
                "filingDate": [
                    "2024-11-01",
                    "2024-12-01",
                    "2025-01-31",
                    "2023-11-03",
                    "2025-02-01",
                ],
                "reportDate": [
                    "2024-09-28",
                    "2024-09-28",
                    "2024-12-28",
                    "2023-09-30",
                    "2025-01-15",
                ],
                "primaryDocument": [
                    "aapl-20240928.htm",
                    "aapl-20240928a.htm",
                    "aapl-20241228.htm",
                    "aapl-20230930.htm",
                    "ex99.htm",
                ],
            },
            "files": [],
        },
    }


def _index_payload(primary: str, xbrl: str) -> dict:
    return {
        "directory": {
            "item": [
                {"name": primary, "type": "10-K"},
                {"name": xbrl, "type": "EX-101.INS"},
                {"name": "FilingSummary.xml", "type": "XML"},
            ]
        }
    }


@pytest.fixture
def collector_env(tmp_path: Path):
    db = FilingDatabase(db_path=tmp_path / "hap.db")
    cache_dir = tmp_path / "filings"
    collector = FilingCollector(
        database=db,
        cache_dir=cache_dir,
        request_delay_seconds=0,
    )

    ticker_map = {"AAPL": "320193"}
    submissions = _submissions_payload()

    def fake_get_json(url: str) -> dict:
        if "company_tickers.json" in url:
            return {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}
        if "submissions/CIK" in url:
            return submissions
        if url.endswith("/index.json"):
            if "000032019324000200" in url:
                return _index_payload("aapl-20240928a.htm", "aapl-20240928a_htm.xml")
            if "000032019325000010" in url:
                return _index_payload("aapl-20241228.htm", "aapl-20241228_htm.xml")
            if "000032019323000100" in url:
                return _index_payload("aapl-20230930.htm", "aapl-20230930_htm.xml")
            return _index_payload("aapl-20240928.htm", "aapl-20240928_htm.xml")
        raise AssertionError(f"Unexpected JSON URL: {url}")

    def fake_get_bytes(url: str) -> bytes:
        return f"content:{url}".encode("utf-8")

    collector._get_json = fake_get_json  # type: ignore[method-assign]
    collector._get_bytes = fake_get_bytes  # type: ignore[method-assign]
    collector._load_ticker_map = lambda: ticker_map  # type: ignore[method-assign]
    return collector, db, cache_dir


def test_collect_resolves_cik_prefers_amendment_and_caches_documents(collector_env):
    collector, db, cache_dir = collector_env

    result = collector.collect(
        CollectFilingsRequest(ticker="aapl", historical_years=10, download_documents=True)
    )

    assert result.status == "completed"
    assert result.cik == "0000320193"
    assert result.latest_10k is not None
    assert result.latest_10k.form == "10-K/A"
    assert result.latest_10k.is_amendment is True
    assert result.latest_10k.selected_role == "latest_10k"
    assert result.latest_10k.accession_number == "0000320193-24-000200"

    assert result.latest_10q is not None
    assert result.latest_10q.form == "10-Q"
    assert result.latest_10q.selected_role == "latest_10q"

    assert len(result.historical_10ks) >= 1
    assert all(item.base_form == "10-K" for item in result.historical_10ks)

    assert result.latest_10k.html_path is not None
    assert Path(result.latest_10k.html_path).exists()
    assert result.latest_10k.xbrl_path is not None
    assert Path(result.latest_10k.xbrl_path).exists()

    stored = db.get_collection(result.collection_id)
    assert stored is not None
    assert stored.latest_10k is not None
    assert stored.latest_10k.accession_number == result.latest_10k.accession_number
    assert db.get_latest_collection_for_ticker("AAPL") is not None

    # Superseded original 10-K for same report period should be retained.
    assert any(item.selected_role == "superseded" for item in result.filings)


def test_collect_without_downloads_still_stores_metadata(collector_env):
    collector, db, _cache_dir = collector_env
    result = collector.collect(
        CollectFilingsRequest(ticker="AAPL", download_documents=False)
    )
    assert result.latest_10k is not None
    assert result.latest_10k.html_path is None
    assert db.list_filings_for_ticker("AAPL")
    assert "No extraction performed" in result.message


def test_unknown_ticker_raises(collector_env):
    collector, _db, _cache_dir = collector_env
    collector._load_ticker_map = lambda: {"AAPL": "320193"}  # type: ignore[method-assign]
    with pytest.raises(FilingCollectorError, match="Could not resolve CIK"):
        collector.collect(CollectFilingsRequest(ticker="ZZZZ"))


def test_prefer_amendment_helper():
    original = FilingDocumentMeta(
        accession_number="1",
        form="10-K",
        base_form="10-K",
        is_amendment=False,
        filing_date="2024-11-01",
        report_date="2024-09-28",
    )
    amendment = FilingDocumentMeta(
        accession_number="2",
        form="10-K/A",
        base_form="10-K",
        is_amendment=True,
        filing_date="2024-12-01",
        report_date="2024-09-28",
    )
    winner = FilingCollector._prefer_amendment([original, amendment])
    assert winner.accession_number == "2"
