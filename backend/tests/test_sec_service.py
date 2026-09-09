"""Unit tests for SEC fact matching."""

from __future__ import annotations

from services.sec_service import SecService

# Minimal reproduction of Apple FY2018 10-K companyfacts: same filing fy/fp/form,
# two Revenues durations — true FY2018 vs CY2016 comparative.
AAPL_REVENUE_COMPARATIVE_FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "val": 215639000000,
                            "fy": 2018,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2018-11-05",
                            "accn": "0000320193-18-000145",
                            "start": "2015-09-27",
                            "end": "2016-09-24",
                            "frame": "CY2016",
                        },
                        {
                            "val": 265595000000,
                            "fy": 2018,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2018-11-05",
                            "accn": "0000320193-18-000145",
                            "start": "2017-10-01",
                            "end": "2018-09-29",
                            "frame": "CY2018",
                        },
                    ]
                },
            },
            "SalesRevenueNet": {
                "label": "Sales Revenue, Net",
                "units": {
                    "USD": [
                        {
                            "val": 215639000000,
                            "fy": 2016,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2016-10-26",
                            "accn": "0001628280-16-020309",
                            "start": "2015-09-27",
                            "end": "2016-09-24",
                        }
                    ]
                },
            },
        }
    }
}


def test_find_fact_matches_revenue(mock_company_facts):
    fact = SecService().find_fact(mock_company_facts, "Revenue", "FY2024")
    assert fact is not None
    assert fact.tag == "Revenues"
    assert fact.value == 391035000000


def test_find_fact_returns_none_when_missing(mock_company_facts):
    fact = SecService().find_fact(mock_company_facts, "Dividends Paid", "FY2024")
    assert fact is None


def test_aapl_fy2018_revenue_not_comparative():
    """Comparative CY2016 in the FY2018 10-K must not win for query FY2018."""
    fact = SecService().find_fact(AAPL_REVENUE_COMPARATIVE_FACTS, "Revenue", "FY2018")
    assert fact is not None
    assert fact.value == 265595000000
    assert fact.frame == "CY2018"


def test_aapl_fy2016_revenue_still_215639():
    fact = SecService().find_fact(AAPL_REVENUE_COMPARATIVE_FACTS, "Revenue", "FY2016")
    assert fact is not None
    assert fact.value == 215639000000


def test_comparative_in_later_10k_not_labeled_as_filing_year():
    """Query FY2018 must not return the CY2016 comparative from that filing."""
    fact = SecService().find_fact(AAPL_REVENUE_COMPARATIVE_FACTS, "Revenue", "FY2018")
    assert fact is not None
    assert fact.value != 215639000000
    # Economic evidence on the selected fact
    assert fact.frame == "CY2018"
