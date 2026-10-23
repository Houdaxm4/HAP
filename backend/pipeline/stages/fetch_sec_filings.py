"""Stage: collect SEC filings and structured XBRL facts."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from services.output_service import OutputService
from services.sec_service import SecService, SecServiceError


class FetchSecFilingsStage:
    """Download SEC filing metadata and company facts for the issuer."""

    def __init__(
        self,
        sec_service: SecService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.sec_service = sec_service or SecService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        cache_dir: Path | None = None,
    ) -> tuple[dict, dict, str, str, DecisionLogEntry]:
        if cache_dir is not None:
            self.sec_service.cache_dir = cache_dir

        cik = self.sec_service.resolve_cik(analysis.ticker)
        manifest = self.sec_service.fetch_filings_manifest(analysis.ticker, cik)
        company_facts = self.sec_service.fetch_company_facts(cik)
        # a company that changed CIK (TPL: Trust -> Corporation): its older 10-Ks and XBRL facts sit under the old CIK
        for old_cik in self.sec_service.predecessor_ciks(analysis.ticker):
            try:
                old_manifest = self.sec_service.fetch_filings_manifest(analysis.ticker, old_cik)
                have = {f.get("accession_number") for f in manifest.get("selected_filings", [])}
                manifest["selected_filings"] = manifest.get("selected_filings", []) + [
                    f
                    for f in old_manifest.get("selected_filings", [])
                    if f.get("filing_type") == "10-K" and f.get("accession_number") not in have
                ]
                manifest.setdefault("predecessor_ciks", []).append(old_cik)
                company_facts = self.sec_service.merge_company_facts(
                    company_facts, self.sec_service.fetch_company_facts(old_cik)
                )
            except SecServiceError:
                continue

        manifest_path = self.output_service.write_json(
            analysis.analysis_id,
            "sec_filings_manifest.json",
            manifest,
        )
        facts_path = self.output_service.write_json(
            analysis.analysis_id,
            "company_facts.json",
            company_facts,
        )

        selected_count = len(manifest.get("selected_filings", []))
        log_entry = DecisionLogEntry(
            agent="Document Collection Agent",
            action="fetch_sec_filings",
            detail=(
                f"Resolved CIK {cik} for {analysis.ticker} and indexed "
                f"{selected_count} priority filings (10-K history + latest 10-Q)."
            ),
            confidence=1.0,
            citations=[manifest_path, facts_path],
        )
        return manifest, company_facts, manifest_path, facts_path, log_entry
