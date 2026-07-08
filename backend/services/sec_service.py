"""SEC EDGAR integration for filing discovery and XBRL fact extraction."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

DEFAULT_USER_AGENT = "HAP-Platform contact@houda-analyst.com"

FILING_PRIORITY = ("10-K", "10-Q", "8-K")


@dataclass
class FilingDocument:
    """Metadata for one downloaded or referenced SEC filing."""

    accession_number: str
    filing_type: str
    filing_date: str
    report_date: str | None
    primary_document: str
    document_url: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None


@dataclass
class XbrlFact:
    """One XBRL fact extracted from SEC company facts."""

    tag: str
    taxonomy: str
    label: str
    unit: str
    value: float
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    filed: str
    accession_number: str | None
    frame: str | None = None


class SecServiceError(Exception):
    """Raised when SEC data cannot be retrieved or parsed."""


class SecService:
    """Download SEC filings and extract XBRL facts for workbook population."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_dir: Path | None = None,
        request_delay_seconds: float = 0.12,
    ) -> None:
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self.request_delay_seconds = request_delay_seconds
        self._last_request_at = 0.0
        self._ticker_map: dict[str, str] | None = None

    def resolve_cik(self, ticker: str) -> str:
        """Map a ticker symbol to a zero-padded 10-digit CIK."""
        ticker_map = self._load_ticker_map()
        cik = ticker_map.get(ticker.upper())
        if not cik:
            raise SecServiceError(f"Could not resolve CIK for ticker '{ticker}'.")
        return cik.zfill(10)

    def fetch_filings_manifest(self, ticker: str, cik: str) -> dict[str, Any]:
        """Return recent filings and company facts metadata for an issuer."""
        submissions = self._get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
        recent = submissions.get("filings", {}).get("recent", {})

        filings: list[FilingDocument] = []
        forms = recent.get("form", [])
        for index, form in enumerate(forms):
            if form not in {"10-K", "10-Q", "8-K", "DEF 14A"}:
                continue
            accession = recent["accessionNumber"][index].replace("-", "")
            primary_document = recent["primaryDocument"][index]
            filing = FilingDocument(
                accession_number=recent["accessionNumber"][index],
                filing_type=form,
                filing_date=recent["filingDate"][index],
                report_date=recent.get("reportDate", [None] * len(forms))[index],
                primary_document=primary_document,
                document_url=(
                    f"{SEC_ARCHIVES_BASE}/{int(cik)}/{accession}/{primary_document}"
                ),
                fiscal_year=self._extract_year(recent.get("reportDate", [None] * len(forms))[index]),
            )
            filings.append(filing)

        ten_k = [f for f in filings if f.filing_type == "10-K"][:10]
        ten_q = [f for f in filings if f.filing_type == "10-Q"][:1]
        selected = ten_k + ten_q

        return {
            "ticker": ticker,
            "cik": cik,
            "company_name": submissions.get("name"),
            "selected_filings": [self._filing_to_dict(filing) for filing in selected],
            "total_filings_scanned": len(filings),
        }

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        """Download structured XBRL company facts for an issuer."""
        cache_path = self._cache_path(cik, "companyfacts.json")
        if cache_path and cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        data = self._get_json(SEC_COMPANY_FACTS_URL.format(cik=cik))
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle)
        return data

    def _candidate_tags(self, concept: str, xbrl_tag_hint: str | None) -> set[str] | None:
        if xbrl_tag_hint:
            return {xbrl_tag_hint}
        normalized = concept.strip().lower()
        aliases = CONCEPT_TO_XBRL.get(normalized)
        if aliases:
            return set(aliases)
        return None

    def find_fact(
        self,
        company_facts: dict[str, Any],
        concept: str,
        period: str,
        xbrl_tag_hint: str | None = None,
    ) -> XbrlFact | None:
        """
        Find the best matching XBRL fact for a concept and reporting period.

        Never fabricates values — returns None when no defensible match exists.
        """
        candidate_tags = self._candidate_tags(concept, xbrl_tag_hint)
        if candidate_tags is None:
            return None

        target_year, target_period = self._parse_period(period)
        facts = company_facts.get("facts", {})
        best_match: XbrlFact | None = None
        best_score = -1

        for taxonomy in ("us-gaap", "dei", "ifrs-full"):
            taxonomy_facts = facts.get(taxonomy, {})
            for tag, payload in taxonomy_facts.items():
                if tag not in candidate_tags:
                    continue
                units = payload.get("units", {})
                for unit, entries in units.items():
                    for entry in entries:
                        score = self._score_fact(entry, target_year, target_period)
                        if score <= 0:
                            continue
                        if score > best_score:
                            best_score = score
                            best_match = XbrlFact(
                                tag=tag,
                                taxonomy=taxonomy,
                                label=payload.get("label", tag),
                                unit=unit,
                                value=float(entry["val"]),
                                fiscal_year=entry.get("fy"),
                                fiscal_period=entry.get("fp"),
                                form=entry.get("form", ""),
                                filed=entry.get("filed", ""),
                                accession_number=entry.get("accn"),
                                frame=entry.get("frame"),
                            )
        return best_match

    @staticmethod
    def _score_fact(entry: dict[str, Any], target_year: int | None, target_period: str | None) -> int:
        score = 0
        fiscal_year = entry.get("fy")
        fiscal_period = entry.get("fp")
        form = entry.get("form", "")

        if target_year is not None and fiscal_year == target_year:
            score += 5
        elif target_year is not None and fiscal_year == target_year - 1 and target_period == "FY":
            score += 2

        if target_period:
            if fiscal_period == target_period:
                score += 4
            elif target_period == "FY" and form == "10-K":
                score += 2
            elif target_period.startswith("Q") and form == "10-Q" and fiscal_period == target_period:
                score += 3

        if form in {"10-K", "10-Q"}:
            score += 1

        if entry.get("val") is None:
            return 0
        return score

    @staticmethod
    def _parse_period(period: str) -> tuple[int | None, str | None]:
        text = period.strip().upper()
        year_match = re.search(r"(20\d{2}|19\d{2})", text)
        year = int(year_match.group(1)) if year_match else None

        if "FY" in text or re.fullmatch(r"20\d{2}|19\d{2}", text):
            return year, "FY"
        quarter_match = re.search(r"Q([1-4])", text)
        if quarter_match:
            return year, f"Q{quarter_match.group(1)}"
        return year, None

    def _load_ticker_map(self) -> dict[str, str]:
        if self._ticker_map is not None:
            return self._ticker_map
        payload = self._get_json(SEC_TICKERS_URL)
        self._ticker_map = {
            str(item["ticker"]).upper(): str(item["cik_str"])
            for item in payload.values()
        }
        return self._ticker_map

    def _get_json(self, url: str) -> dict[str, Any]:
        self._respect_rate_limit()
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code != 200:
                raise SecServiceError(
                    f"SEC request failed ({response.status_code}) for {url}"
                )
            return response.json()

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - elapsed)
        self._last_request_at = time.time()

    def _cache_path(self, cik: str, filename: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / cik / filename

    @staticmethod
    def _extract_year(report_date: str | None) -> int | None:
        if not report_date:
            return None
        match = re.match(r"(20\d{2}|19\d{2})", report_date)
        return int(match.group(1)) if match else None

    @staticmethod
    def _filing_to_dict(filing: FilingDocument) -> dict[str, Any]:
        return {
            "accession_number": filing.accession_number,
            "filing_type": filing.filing_type,
            "filing_date": filing.filing_date,
            "report_date": filing.report_date,
            "primary_document": filing.primary_document,
            "document_url": filing.document_url,
            "fiscal_year": filing.fiscal_year,
            "fiscal_period": filing.fiscal_period,
        }


CONCEPT_TO_XBRL: dict[str, list[str]] = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "total revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "net income": ["NetIncomeLoss", "ProfitLoss"],
    "operating income": ["OperatingIncomeLoss"],
    "gross profit": ["GrossProfit"],
    "total assets": ["Assets"],
    "total liabilities": ["Liabilities"],
    "stockholders equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash and cash equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
    "operating cash flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capital expenditures": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "shares outstanding": [
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ],
    "eps": ["EarningsPerShareBasic", "EarningsPerShareDiluted"],
    "earnings per share": ["EarningsPerShareBasic", "EarningsPerShareDiluted"],
}
