"""Unit tests for SEC fact matching."""

from __future__ import annotations

from services.sec_service import SecService


def test_find_fact_matches_revenue(mock_company_facts):
    fact = SecService().find_fact(mock_company_facts, "Revenue", "FY2024")
    assert fact is not None
    assert fact.tag == "Revenues"
    assert fact.value == 391035000000


def test_find_fact_returns_none_when_missing(mock_company_facts):
    fact = SecService().find_fact(mock_company_facts, "Dividends Paid", "FY2024")
    assert fact is None
