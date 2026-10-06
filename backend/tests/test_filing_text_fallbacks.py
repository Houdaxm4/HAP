from models.new_company import LeaseYearData
from services.new_company_lease_service import NewCompanyLeaseService
from services.new_company_rd_service import NewCompanyRdService

LEASE_NOTE = (
    "Rental expense for the years ended June 30, 2018, 2017, and 2016 was approximately $10.2 million, $8.0 million and $6.6 million. "
    "The gross minimum annual rental commitments under non-cancelable operating leases at June 30, 2018: (in thousands) Lease Sublease "
    "2019 10,202 329 2020 8,704 336 2021 7,923 346 2022 7,095 356 2023 7,204 367 Thereafter 15,995 2,670"
)
RD_NOTE = "Total research and development costs were $5.5 million, $4.9 million and $4.1 million for the years ended June 30, 2017, 2016, and 2015."


class FakeSec:
    """Two filings for the same year: a Part III amendment (10-K/A) listed first and the original 10-K."""

    def __init__(self, original_text: str) -> None:
        self.original_text = original_text
        self.fetched: list[str] = []

    def resolve_cik(self, ticker: str) -> str:
        return "0000000001"

    def list_recent_filings(self, cik, *, forms=None, items_contains=None):
        return [
            {"fiscal_year": 2018, "filing_type": "10-K/A", "document_url": "https://x/amendment.htm"},
            {"fiscal_year": 2018, "filing_type": "10-K", "document_url": "https://x/original.htm"},
        ]

    def fetch_document_text(self, url, *, cik=None, cache_name=None):
        self.fetched.append(url)
        return "<p>Part III directors and officers</p>" if "amendment" in url else f"<p>{self.original_text}</p>"


def test_lease_commitments_come_from_the_original_10k_not_the_amendment():
    sec = FakeSec(LEASE_NOTE)
    rec = LeaseYearData(fiscal_year="FY2018", regime="pre_asc_842")
    out, raw = NewCompanyLeaseService._commitments_from_filing(sec, "SXI", "FY2018", rec, [], {})
    assert sec.fetched == ["https://x/original.htm"]
    assert (out.year_1, out.year_5, out.thereafter, out.regime, out.lease_cost) == (10.202, 7.204, 15.995, "pre_asc_842", 10.2)
    assert raw and raw[0]["label"].startswith("sec_10k_text:operating_lease_commitments")


def test_a_year_without_a_commitments_table_stays_empty():
    rec = LeaseYearData(fiscal_year="FY2018")
    out, raw = NewCompanyLeaseService._commitments_from_filing(FakeSec("The Company leases offices."), "SXI", "FY2018", rec, [], {})
    assert out.year_1 is None and raw == []


def test_rd_expense_is_read_from_the_filing_note_of_that_year_or_the_next_two():
    class RdSec(FakeSec):
        def list_recent_filings(self, cik, *, forms=None, items_contains=None):
            return [{"fiscal_year": 2017, "filing_type": "10-K", "document_url": "https://x/2017.htm"}]

        def fetch_document_text(self, url, *, cik=None, cache_name=None):
            return f"<p>{RD_NOTE}</p>"

    cache: dict = {}
    found = NewCompanyRdService._rd_from_filings(RdSec(RD_NOTE), "SXI", ["FY2016"], cache)
    assert found["FY2016"][0] == 4.9 and found["FY2016"][1].startswith("sec_10k_text:research_and_development_note")
    assert NewCompanyRdService._rd_from_filings(RdSec(RD_NOTE), "SXI", ["FY2010"], cache) == {}      # no filing within two years
