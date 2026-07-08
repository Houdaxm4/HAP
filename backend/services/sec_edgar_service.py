"""SEC EDGAR filing collection and XBRL fact lookup."""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

import httpx

from models.sec import FilingRecord, SecCompanyProfile, SecFilingBundle

SEC_USER_AGENT = "HAP-Platform/0.4 (contact@hap.local)"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_document}"
)

CONCEPT_ALIASES: dict[str, list[str]] = {
    "revenues": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "sales": ["Revenues", "SalesRevenueNet"],
    "netincome": ["NetIncomeLoss", "ProfitLoss"],
    "net income": ["NetIncomeLoss", "ProfitLoss"],
    "netincomeloss": ["NetIncomeLoss"],
    "assets": ["Assets"],
    "totassets": ["Assets"],
    "liabilities": ["Liabilities"],
    "stockholdersequity": ["StockholdersEquity"],
    "equity": ["StockholdersEquity"],
    "eps": ["EarningsPerShareBasic"],
    "epsbasic": ["EarningsPerShareBasic"],
    "epsdiluted": ["EarningsPerShareDiluted"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "cashandcashequivalents": ["CashAndCashEquivalentsAtCarryingValue"],
}


class SecEdgarError(Exception):
    """Raised when SEC data cannot be retrieved."""


class SecEdgarService:
    """Download SEC filings and resolve XBRL facts for workbook filling."""

    def __init__(self, filings_dir: Path | None = None) -> None:
        self.filings_dir = filings_dir

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=60.0,
            follow_redirects=True,
        )

    def resolve_company(self, ticker: str) -> SecCompanyProfile:
        normalized = ticker.strip().upper()
        with self._client() as client:
            response = client.get(COMPANY_TICKERS_URL)
            response.raise_for_status()
            payload = response.json()

        for entry in payload.values():
            if str(entry.get("ticker", "")).upper() == normalized:
                cik = str(entry["cik_str"]).zfill(10)
                return SecCompanyProfile(
                    ticker=normalized,
                    cik=cik,
                    company_name=str(entry.get("title", normalized)),
                )

        raise SecEdgarError(f"Ticker '{normalized}' was not found in SEC company tickers.")

    def collect_filings(
        self,
        profile: SecCompanyProfile,
        analysis_id: str,
        ten_k_years: int = 10,
    ) -> SecFilingBundle:
        with self._client() as client:
            submissions = self._fetch_submissions(client, profile.cik)
            ten_k_candidates = self._select_filings(submissions, "10-K", ten_k_years)
            ten_q_candidates = self._select_filings(submissions, "10-Q", 1)

            filing_dir = self._ensure_filing_dir(analysis_id)
            ten_k_records = [
                self._download_filing(client, profile, filing, filing_dir / "10-K")
                for filing in ten_k_candidates
            ]
            latest_ten_q = None
            if ten_q_candidates:
                latest_ten_q = self._download_filing(
                    client,
                    profile,
                    ten_q_candidates[0],
                    filing_dir / "10-Q",
                )

            time.sleep(0.2)
            return SecFilingBundle(
                profile=profile,
                ten_k_filings=ten_k_records,
                latest_ten_q=latest_ten_q,
            )

    def lookup_fact(
        self,
        profile: SecCompanyProfile,
        concept: str,
        period: str,
    ) -> tuple[float | int | str | None, str | None]:
        with self._client() as client:
            response = client.get(COMPANY_FACTS_URL.format(cik=profile.cik))
            response.raise_for_status()
            facts_payload = response.json()

        tags = self._resolve_tags(concept)
        us_gaap = facts_payload.get("facts", {}).get("us-gaap", {})
        for tag in tags:
            if tag not in us_gaap:
                continue
            units = us_gaap[tag].get("units", {})
            for unit_values in units.values():
                selected = self._select_fact(unit_values, period)
                if selected is not None:
                    return selected, tag
        return None, None

    def _fetch_submissions(self, client: httpx.Client, cik: str) -> dict:
        response = client.get(SUBMISSIONS_URL.format(cik=cik))
        response.raise_for_status()
        return response.json()

    def _select_filings(
        self,
        submissions: dict,
        form_type: str,
        limit: int,
    ) -> list[dict]:
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        selected: list[dict] = []

        for index, form in enumerate(forms):
            if form != form_type:
                continue
            selected.append(
                {
                    "form": form,
                    "filing_date": recent["filingDate"][index],
                    "accession_number": recent["accessionNumber"][index],
                    "primary_document": recent["primaryDocument"][index],
                    "report_date": recent.get("reportDate", [None])[index],
                }
            )
            if len(selected) >= limit:
                break
        return selected

    def _download_filing(
        self,
        client: httpx.Client,
        profile: SecCompanyProfile,
        filing: dict,
        target_dir: Path,
    ) -> FilingRecord:
        target_dir.mkdir(parents=True, exist_ok=True)
        accession = filing["accession_number"]
        accession_path = accession.replace("-", "")
        cik_short = str(int(profile.cik))
        url = ARCHIVE_URL.format(
            cik=cik_short,
            accession=accession_path,
            primary_document=filing["primary_document"],
        )
        response = client.get(url)
        response.raise_for_status()

        filename = f"{filing['form']}_{filing['filing_date']}_{accession_path}.html"
        destination = target_dir / filename
        destination.write_bytes(response.content)

        fiscal_year = None
        report_date = filing.get("report_date")
        if report_date:
            fiscal_year = datetime.strptime(report_date, "%Y-%m-%d").year

        return FilingRecord(
            form=filing["form"],
            filing_date=filing["filing_date"],
            accession_number=accession,
            primary_document=filing["primary_document"],
            fiscal_year=fiscal_year,
            local_path=str(destination),
            source_url=url,
        )

    def _ensure_filing_dir(self, analysis_id: str) -> Path:
        if self.filings_dir is None:
            self.filings_dir = (
                Path(__file__).resolve().parent.parent / "storage" / "filings"
            )
        directory = self.filings_dir / analysis_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _resolve_tags(self, concept: str) -> list[str]:
        normalized = re.sub(r"[^a-z0-9 ]", "", concept.lower()).strip()
        if normalized in CONCEPT_ALIASES:
            return CONCEPT_ALIASES[normalized]
        compact = normalized.replace(" ", "")
        if compact in CONCEPT_ALIASES:
            return CONCEPT_ALIASES[compact]
        # Allow direct us-gaap tag names from the filter file.
        pascal = "".join(part.capitalize() for part in re.split(r"[\s_]+", concept) if part)
        return [concept, pascal, compact.capitalize()]

    def _select_fact(
        self,
        values: list[dict],
        period: str,
    ) -> float | int | None:
        if not values:
            return None

        normalized_period = period.lower().strip()
        annual = [item for item in values if item.get("fp") == "FY" and item.get("form") == "10-K"]
        quarterly = [item for item in values if item.get("fp") in {"Q1", "Q2", "Q3", "Q4", "FY"}]

        if normalized_period.startswith("fy") and normalized_period[2:].isdigit():
            year = int(normalized_period[2:])
            for item in sorted(annual, key=lambda row: row.get("end", ""), reverse=True):
                if item.get("fy") == year:
                    return item.get("val")
            return None

        if normalized_period.isdigit():
            year = int(normalized_period)
            for item in sorted(annual, key=lambda row: row.get("end", ""), reverse=True):
                if item.get("fy") == year:
                    return item.get("val")
            return None

        if normalized_period in {"latest_quarterly", "quarterly", "latest_10q"}:
            pool = quarterly or values
        else:
            pool = annual or values

        if not pool:
            return None

        latest = sorted(pool, key=lambda row: row.get("end", ""), reverse=True)[0]
        return latest.get("val")
