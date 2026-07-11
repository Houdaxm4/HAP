"""Filing Collector — download SEC 10-K / 10-Q filings without extraction."""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from models.common import utc_now_iso
from models.filings import (
    CollectFilingsRequest,
    FilingCollectionResult,
    FilingDocumentMeta,
)
from services.filing_db import FilingDatabase
from services.sec_service import DEFAULT_USER_AGENT, SEC_ARCHIVES_BASE, SEC_SUBMISSIONS_URL, SEC_TICKERS_URL, SecServiceError

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "storage" / "filings"

TARGET_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}


class FilingCollectorError(Exception):
    """Raised when filing collection fails."""


class FilingCollector:
    """
    Collect SEC filings for a ticker.

    - Resolve CIK via SEC company tickers
    - Discover latest 10-K, latest 10-Q, and historical 10-Ks
    - Prefer amended filings (10-K/A, 10-Q/A) when they supersede originals
    - Download HTML primary documents and XBRL instance files
    - Cache documents locally and store metadata in SQLite

    Does not extract financial values.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_dir: Path | None = None,
        database: FilingDatabase | None = None,
        request_delay_seconds: float = 0.12,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.database = database or FilingDatabase()
        self.request_delay_seconds = request_delay_seconds
        self._last_request_at = 0.0
        self._ticker_map: dict[str, str] | None = None
        self._http_client = http_client

    def collect(self, request: CollectFilingsRequest) -> FilingCollectionResult:
        """Collect filings for a ticker and persist metadata + cached documents."""
        ticker = request.ticker.strip().upper()
        collection_id = str(uuid.uuid4())
        created_at = utc_now_iso()
        cik = ""
        company_name: str | None = None

        try:
            cik = self.resolve_cik(ticker)
            submissions = self._fetch_submissions(cik)
            company_name = submissions.get("name")
            raw_filings = self._discover_filings(cik, submissions)
            selected = self._select_filings(raw_filings, historical_years=request.historical_years)

            issuer_cache = self.cache_dir / cik
            issuer_cache.mkdir(parents=True, exist_ok=True)

            if request.download_documents:
                for filing in selected:
                    self._download_filing_documents(cik, filing, issuer_cache)

            result = FilingCollectionResult(
                collection_id=collection_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                status="completed",
                latest_10k=next((f for f in selected if f.selected_role == "latest_10k"), None),
                latest_10q=next((f for f in selected if f.selected_role == "latest_10q"), None),
                historical_10ks=[f for f in selected if f.selected_role == "historical_10k"],
                filings=selected,
                cache_dir=str(issuer_cache),
                created_at=created_at,
                completed_at=utc_now_iso(),
                message=(
                    "Filings collected and cached. "
                    "HTML/XBRL downloaded where available. No extraction performed."
                ),
            )
            self.database.save_collection(result, historical_years=request.historical_years)
            return result
        except (FilingCollectorError, SecServiceError, OSError, httpx.HTTPError, ValueError) as exc:
            if cik:
                failed = FilingCollectionResult(
                    collection_id=collection_id,
                    ticker=ticker,
                    cik=cik,
                    company_name=company_name,
                    status="failed",
                    created_at=created_at,
                    completed_at=utc_now_iso(),
                    error=str(exc),
                    message="Filing collection failed. No extraction performed.",
                )
                try:
                    self.database.save_collection(failed, historical_years=request.historical_years)
                except Exception:  # noqa: BLE001 — never mask the original collector error
                    pass
            raise FilingCollectorError(str(exc)) from exc

    def resolve_cik(self, ticker: str) -> str:
        """Map a ticker symbol to a zero-padded 10-digit CIK."""
        ticker_map = self._load_ticker_map()
        cik = ticker_map.get(ticker.upper())
        if not cik:
            raise FilingCollectorError(f"Could not resolve CIK for ticker '{ticker}'.")
        return str(cik).zfill(10)

    def get_collection(self, collection_id: str) -> FilingCollectionResult | None:
        return self.database.get_collection(collection_id)

    def get_filings_for_ticker(self, ticker: str) -> FilingCollectionResult | None:
        return self.database.get_latest_collection_for_ticker(ticker)

    def _discover_filings(self, cik: str, submissions: dict[str, Any]) -> list[FilingDocumentMeta]:
        filings = self._parse_recent_filings(cik, submissions.get("filings", {}).get("recent", {}))

        # Pull older submission shards when present for deeper 10-K history.
        for shard in submissions.get("filings", {}).get("files", []) or []:
            name = shard.get("name")
            if not name:
                continue
            shard_url = f"https://data.sec.gov/submissions/{name}"
            shard_payload = self._get_json(shard_url)
            filings.extend(self._parse_recent_filings(cik, shard_payload))

        # De-duplicate by accession number, preferring richer rows.
        by_accession: dict[str, FilingDocumentMeta] = {}
        for filing in filings:
            existing = by_accession.get(filing.accession_number)
            if existing is None or (filing.is_amendment and not existing.is_amendment):
                by_accession[filing.accession_number] = filing
        return list(by_accession.values())

    def _parse_recent_filings(self, cik: str, recent: dict[str, Any]) -> list[FilingDocumentMeta]:
        forms = recent.get("form", []) or []
        accessions = recent.get("accessionNumber", []) or []
        filing_dates = recent.get("filingDate", []) or []
        report_dates = recent.get("reportDate", []) or []
        primary_docs = recent.get("primaryDocument", []) or []

        filings: list[FilingDocumentMeta] = []
        for index, form in enumerate(forms):
            if form not in TARGET_FORMS:
                continue
            accession = accessions[index]
            accession_nodash = accession.replace("-", "")
            primary_document = primary_docs[index] if index < len(primary_docs) else None
            report_date = report_dates[index] if index < len(report_dates) else None
            filing_date = filing_dates[index] if index < len(filing_dates) else ""
            base_form = "10-K" if form.startswith("10-K") else "10-Q"
            primary_url = None
            if primary_document:
                primary_url = f"{SEC_ARCHIVES_BASE}/{int(cik)}/{accession_nodash}/{primary_document}"

            filings.append(
                FilingDocumentMeta(
                    accession_number=accession,
                    form=form,
                    base_form=base_form,  # type: ignore[arg-type]
                    is_amendment=form.endswith("/A"),
                    filing_date=filing_date,
                    report_date=report_date or None,
                    primary_document=primary_document,
                    primary_document_url=primary_url,
                    index_url=f"{SEC_ARCHIVES_BASE}/{int(cik)}/{accession_nodash}/index.json",
                    html_url=primary_url if primary_document and primary_document.lower().endswith((".htm", ".html")) else None,
                    fiscal_year=self._extract_year(report_date),
                )
            )
        return filings

    def _select_filings(
        self,
        filings: list[FilingDocumentMeta],
        *,
        historical_years: int,
    ) -> list[FilingDocumentMeta]:
        """
        Choose latest 10-K, latest 10-Q, and historical 10-Ks.

        Amended filings supersede originals for the same report period when newer.
        """
        ten_k_groups = self._group_by_report_period(
            [f for f in filings if f.base_form == "10-K"]
        )
        ten_q_groups = self._group_by_report_period(
            [f for f in filings if f.base_form == "10-Q"]
        )

        preferred_10ks = [self._prefer_amendment(group) for group in ten_k_groups.values()]
        preferred_10qs = [self._prefer_amendment(group) for group in ten_q_groups.values()]

        preferred_10ks.sort(key=lambda item: item.filing_date, reverse=True)
        preferred_10qs.sort(key=lambda item: item.filing_date, reverse=True)

        cutoff = date.today() - timedelta(days=365 * historical_years)
        historical_candidates = [
            filing
            for filing in preferred_10ks
            if self._parse_date(filing.filing_date) is None
            or self._parse_date(filing.filing_date) >= cutoff  # type: ignore[operator]
        ]

        selected: list[FilingDocumentMeta] = []
        latest_10k = historical_candidates[0] if historical_candidates else None
        if latest_10k is not None:
            latest_10k.selected_role = "latest_10k"
            selected.append(latest_10k)
            for filing in historical_candidates[1:]:
                filing.selected_role = "historical_10k"
                selected.append(filing)

        latest_10q = preferred_10qs[0] if preferred_10qs else None
        if latest_10q is not None:
            latest_10q.selected_role = "latest_10q"
            selected.append(latest_10q)

        # Keep superseded originals in metadata for auditability when an amendment won.
        selected_accessions = {filing.accession_number for filing in selected}
        for group in list(ten_k_groups.values()) + list(ten_q_groups.values()):
            winner = self._prefer_amendment(group)
            for filing in group:
                if filing.accession_number == winner.accession_number:
                    continue
                if filing.accession_number in selected_accessions:
                    continue
                filing.selected_role = "superseded"
                selected.append(filing)

        return selected

    def _group_by_report_period(
        self,
        filings: list[FilingDocumentMeta],
    ) -> dict[str, list[FilingDocumentMeta]]:
        groups: dict[str, list[FilingDocumentMeta]] = {}
        for filing in filings:
            key = filing.report_date or f"{filing.fiscal_year or 'unknown'}:{filing.filing_date}"
            groups.setdefault(key, []).append(filing)
        return groups

    @staticmethod
    def _prefer_amendment(group: list[FilingDocumentMeta]) -> FilingDocumentMeta:
        """Prefer the newest amendment; otherwise the newest original filing."""
        return sorted(
            group,
            key=lambda item: (item.is_amendment, item.filing_date, item.accession_number),
            reverse=True,
        )[0]

    def _download_filing_documents(
        self,
        cik: str,
        filing: FilingDocumentMeta,
        issuer_cache: Path,
    ) -> None:
        accession_dir = issuer_cache / filing.accession_number.replace("-", "")
        accession_dir.mkdir(parents=True, exist_ok=True)

        index_payload = None
        if filing.index_url:
            index_path = accession_dir / "index.json"
            if index_path.exists():
                index_payload = json.loads(index_path.read_text(encoding="utf-8"))
            else:
                try:
                    index_payload = self._get_json(filing.index_url)
                    index_path.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")
                except FilingCollectorError:
                    index_payload = None

        html_url = filing.html_url or filing.primary_document_url
        xbrl_url = None

        if index_payload:
            html_url, xbrl_url = self._pick_document_urls(cik, filing, index_payload)

        if html_url:
            html_name = Path(html_url).name or "primary.htm"
            html_path = accession_dir / html_name
            if not html_path.exists():
                content = self._get_bytes(html_url)
                html_path.write_bytes(content)
            filing.html_url = html_url
            filing.html_path = str(html_path)

        if xbrl_url:
            xbrl_name = Path(xbrl_url).name or "filing.xml"
            xbrl_path = accession_dir / xbrl_name
            if not xbrl_path.exists():
                content = self._get_bytes(xbrl_url)
                xbrl_path.write_bytes(content)
            filing.xbrl_url = xbrl_url
            filing.xbrl_path = str(xbrl_path)

    def _pick_document_urls(
        self,
        cik: str,
        filing: FilingDocumentMeta,
        index_payload: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        directory = f"{SEC_ARCHIVES_BASE}/{int(cik)}/{filing.accession_number.replace('-', '')}"
        items = index_payload.get("directory", {}).get("item", []) or []
        html_url = filing.html_url or filing.primary_document_url
        xbrl_url = None

        # Prefer explicit primary document when it is HTML.
        if filing.primary_document and filing.primary_document.lower().endswith((".htm", ".html")):
            html_url = f"{directory}/{filing.primary_document}"

        xml_candidates: list[tuple[int, str]] = []
        for item in items:
            name = str(item.get("name", ""))
            lower = name.lower()
            item_type = str(item.get("type", "")).upper()
            if not name:
                continue
            if html_url is None and lower.endswith((".htm", ".html")) and "index" not in lower:
                html_url = f"{directory}/{name}"
            if lower.endswith(".xml") and "xsl" not in lower:
                score = 0
                if lower.endswith("_htm.xml") or lower.endswith(".htm.xml"):
                    score += 5
                if "EXTRACTED" in item_type or "XBRL" in item_type or item_type in {"10-K", "10-Q", "10-K/A", "10-Q/A"}:
                    score += 3
                if "exhibit" in lower or lower.startswith("r"):
                    score -= 2
                xml_candidates.append((score, f"{directory}/{name}"))

        if xml_candidates:
            xml_candidates.sort(key=lambda pair: pair[0], reverse=True)
            xbrl_url = xml_candidates[0][1]

        return html_url, xbrl_url

    def _fetch_submissions(self, cik: str) -> dict[str, Any]:
        return self._get_json(SEC_SUBMISSIONS_URL.format(cik=cik))

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
        response = self._request(url, accept="application/json")
        try:
            return response.json()
        except ValueError as exc:
            raise FilingCollectorError(f"Invalid JSON from SEC for {url}") from exc

    def _get_bytes(self, url: str) -> bytes:
        response = self._request(url, accept="*/*")
        return response.content

    def _request(self, url: str, *, accept: str) -> httpx.Response:
        self._respect_rate_limit()
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Encoding": "gzip, deflate",
        }
        client = self._http_client
        owns_client = client is None
        if client is None:
            client = httpx.Client(timeout=60.0, headers=headers, follow_redirects=True)
        try:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                raise FilingCollectorError(
                    f"SEC request failed ({response.status_code}) for {url}"
                )
            return response
        finally:
            if owns_client:
                client.close()

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - elapsed)
        self._last_request_at = time.time()

    @staticmethod
    def _extract_year(report_date: str | None) -> int | None:
        if not report_date:
            return None
        match = re.match(r"(20\d{2}|19\d{2})", report_date)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
