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
