"""Select the smallest 10-K set that covers all ten displayed fiscal years."""

from __future__ import annotations

from typing import Any

from models.new_company import (
    CoverageStatus,
    FilingYearCoverage,
    TenYearSourceCoverageReport,
)
from services.sec_service import SecService

_SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


def _fy_int(token: str) -> int:
    digits = "".join(ch for ch in str(token) if ch.isdigit())
    return int(digits) if digits else 0


def _filing_year(filing: dict[str, Any]) -> int | None:
    fy = filing.get("fiscal_year")
    if isinstance(fy, int):
        return fy
    report = filing.get("report_date") or filing.get("period_end") or ""
    digits = "".join(ch for ch in str(report) if ch.isdigit())
    if len(digits) >= 4:
        return int(digits[:4])
    return None


class NewCompanySecCoverageService:
    """Map each displayed FY to the most recently restated 10-K that covers it."""

    def __init__(self, sec_service: SecService | None = None) -> None:
        self.sec = sec_service or SecService()

    def build(
        self,
        *,
        analysis_id: str,
        ticker: str,
        fiscal_years: list[str],
        sec_manifest: dict[str, Any] | None,
        company_facts: dict[str, Any] | None = None,
        extra_lookback_years: list[str] | None = None,
    ) -> TenYearSourceCoverageReport:
        displayed = list(fiscal_years)
        lookback = [y for y in (extra_lookback_years or []) if y not in displayed]
        required = displayed + lookback
        filings = list((sec_manifest or {}).get("selected_filings") or [])
        ten_k = [
            f
            for f in filings
            if str(f.get("filing_type") or f.get("form") or "").upper() in {"10-K", "10-K/A", "10-KT"}
        ]
        ten_k.sort(key=lambda f: str(f.get("filing_date") or ""), reverse=True)

        # Prefer later-filed (restated) coverage. A typical 10-K supplies three
        # comparative years; we still assign each FY independently because
        # transition reports and year-end changes can yield 1–2 usable years.
        year_to_filing: dict[str, dict[str, Any]] = {}
        overlapping: list[str] = []
        for fy in required:
            year = _fy_int(fy)
            chosen = self._choose_filing(ten_k, year, company_facts)
            if chosen:
                if fy in year_to_filing:
                    overlapping.append(fy)
                year_to_filing[fy] = chosen

        selected_accn: dict[str, dict[str, Any]] = {}
        for filing in year_to_filing.values():
            accn = str(filing.get("accession_number") or "")
            if accn and accn not in selected_accn:
                selected_accn[accn] = filing

        years_out: list[FilingYearCoverage] = []
        for fy in required:
            filing = year_to_filing.get(fy)
            if not filing:
                years_out.append(
                    FilingYearCoverage(
                        fiscal_year=fy,
                        coverage_status=CoverageStatus.MISSING,
                        notes=[
                            "TEN_YEAR_SEC_COVERAGE_INCOMPLETE"
                            if fy in displayed
                            else "RD_LOOKBACK_COVERAGE_INCOMPLETE"
                        ],
                    )
                )
                continue
            form = str(filing.get("filing_type") or filing.get("form") or "10-K")
            amended = form.endswith("/A")
            transition = "KT" in form.upper() or bool(filing.get("transition_report"))
            restated = self._is_restated(filing, fy, company_facts)
            status = CoverageStatus.COVERED_ORIGINAL
            if restated:
                status = CoverageStatus.COVERED_RESTATED
            elif self._is_comparative(filing, fy):
                status = CoverageStatus.COVERED_COMPARATIVE
            if transition:
                status = CoverageStatus.TRANSITION
            if amended:
                status = CoverageStatus.AMENDED
            years_out.append(
                FilingYearCoverage(
                    fiscal_year=fy,
                    filing_used=form,
                    accession_number=filing.get("accession_number"),
                    filing_url=filing.get("document_url") or self._url(sec_manifest, filing),
                    period_end=filing.get("report_date") or filing.get("period_end"),
                    form_type=form,
                    originally_reported_or_revised="retrospectively_revised" if restated else "originally_reported",
                    source_table_or_note="SEC companyfacts / 10-K financial statements",
                    coverage_status=status,
                    restated=restated,
                    transition_report=transition,
                    amended=amended,
                )
            )

        selected = list(selected_accn.values())
        pattern = self._pattern(selected, displayed)
        missing = [y.fiscal_year for y in years_out if y.coverage_status == CoverageStatus.MISSING]
        displayed_missing = [y for y in missing if y in displayed]
        lookback_missing = [y for y in missing if y in lookback]
        warnings: list[str] = []
        if displayed_missing:
            warnings.append("TEN_YEAR_SEC_COVERAGE_INCOMPLETE: missing " + ", ".join(displayed_missing))
        if lookback_missing:
            warnings.append("RD_LOOKBACK_COVERAGE_INCOMPLETE: missing " + ", ".join(lookback_missing))

        return TenYearSourceCoverageReport(
            analysis_id=analysis_id,
            ticker=ticker,
            required_years=required,
            displayed_years=displayed,
            lookback_years=lookback,
            filings_selected=[
                {
                    "accession_number": f.get("accession_number"),
                    "form": f.get("filing_type") or f.get("form"),
                    "filing_date": f.get("filing_date"),
                    "report_date": f.get("report_date"),
                    "document_url": f.get("document_url"),
                    "fiscal_year": f.get("fiscal_year"),
                }
                for f in selected
            ],
            years=years_out,
            overlapping_years_deduped=sorted(set(overlapping)),
            pattern=pattern,
            complete=not displayed_missing,
            lookback_complete=not lookback_missing,
            warnings=warnings,
            summary=(
                f"SEC coverage: displayed {len(displayed) - len(displayed_missing)}/{len(displayed)}; "
                f"lookback {len(lookback) - len(lookback_missing)}/{len(lookback)} from "
                f"{len(selected)} filings ({pattern or 'irregular'}); "
                f"displayed_missing={displayed_missing or 'none'}."
            ),
        )

    def _choose_filing(
        self,
        ten_k: list[dict[str, Any]],
        year: int,
        company_facts: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Prefer the latest 10-K whose filing FY or comparative window covers ``year``."""
        exact: list[dict[str, Any]] = []
        comparative: list[dict[str, Any]] = []
        for filing in ten_k:
            fy = _filing_year(filing)
            form = str(filing.get("filing_type") or "").upper()
            if fy == year:
                exact.append(filing)
            elif fy is not None and year in {fy, fy - 1, fy - 2}:
                comparative.append(filing)
            elif "KT" in form and fy is not None and abs(fy - year) <= 1:
                comparative.append(filing)
        pool = exact or comparative
        if not pool:
            # Fall back: companyfacts prove the year exists even if manifest truncated.
            if company_facts and self._facts_cover_year(company_facts, year):
                return {
                    "filing_type": "10-K",
                    "accession_number": self._latest_accn(company_facts, year),
                    "fiscal_year": year,
                    "report_date": f"{year}-12-31",
                    "document_url": None,
                    "from_companyfacts": True,
                }
            return None
        # Most recently filed wins (restatements / amendments).
        pool.sort(key=lambda f: (str(f.get("filing_date") or ""), str(f.get("accession_number") or "")), reverse=True)
        return pool[0]

    @staticmethod
    def _is_comparative(filing: dict[str, Any], fy_token: str) -> bool:
        fy = _filing_year(filing)
        year = _fy_int(fy_token)
        return fy is not None and fy != year

    @staticmethod
    def _is_restated(
        filing: dict[str, Any], fy_token: str, company_facts: dict[str, Any] | None
    ) -> bool:
        fy = _filing_year(filing)
        year = _fy_int(fy_token)
        if fy is not None and fy > year:
            return True
        form = str(filing.get("filing_type") or "")
        if form.endswith("/A"):
            return True
        return bool(filing.get("from_companyfacts")) and fy is not None and fy != year

    @staticmethod
    def _facts_cover_year(company_facts: dict[str, Any], year: int) -> bool:
        us_gaap = (company_facts.get("facts") or {}).get("us-gaap") or {}
        for tag in (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "NetIncomeLoss",
            "ResearchAndDevelopmentExpense",
        ):
            units = (us_gaap.get(tag) or {}).get("units") or {}
            for entries in units.values():
                for entry in entries:
                    if entry.get("form") not in {"10-K", "10-K/A", "10-KT"}:
                        continue
                    if entry.get("fy") == year or str(entry.get("frame") or "") == f"CY{year}":
                        if entry.get("val") is not None:
                            return True
                    end = str(entry.get("end") or "")
                    if end.startswith(str(year)) and entry.get("fp") == "FY":
                        return True
        return False

    @staticmethod
    def _latest_accn(company_facts: dict[str, Any], year: int) -> str | None:
        us_gaap = (company_facts.get("facts") or {}).get("us-gaap") or {}
        best = None
        best_filed = ""
        for tag in ("Revenues", "NetIncomeLoss"):
            units = (us_gaap.get(tag) or {}).get("units") or {}
            for entries in units.values():
                for entry in entries:
                    if entry.get("fy") != year and str(entry.get("frame") or "") != f"CY{year}":
                        continue
                    filed = str(entry.get("filed") or "")
                    if filed >= best_filed:
                        best_filed = filed
                        best = entry.get("accn")
        return best

    @staticmethod
    def _url(manifest: dict[str, Any] | None, filing: dict[str, Any]) -> str | None:
        if filing.get("document_url"):
            return filing["document_url"]
        cik = str((manifest or {}).get("cik") or "").lstrip("0")
        accn = str(filing.get("accession_number") or "").replace("-", "")
        doc = filing.get("primary_document") or ""
        if cik and accn and doc:
            return f"{_SEC_ARCHIVES}/{cik}/{accn}/{doc}"
        return None

    @staticmethod
    def _pattern(selected: list[dict[str, Any]], required: list[str]) -> str | None:
        n = len(selected)
        if n == 0:
            return None
        if n == 4 and len(required) >= 10:
            return "3+3+3+1"
        if n <= 4:
            return f"{n}_filings_comparative_window"
        return f"{n}_filings"
