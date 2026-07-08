"""Stage: populate workbook cells from SEC facts with full provenance."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.custom_run import CustomRunMapping
from models.pipeline import DecisionLogEntry
from models.provenance import CellProvenance, ProvenanceReport
from models.workbook_schema import WorkbookStructure
from services.output_service import OutputService
from services.sec_service import SecService, XbrlFact
from services.workbook_service import WorkbookService


class FillWorkbookStage:
    """Fill only custom_run cells and record explainability metadata."""

    def __init__(
        self,
        workbook_service: WorkbookService | None = None,
        sec_service: SecService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.workbook_service = workbook_service or WorkbookService()
        self.sec_service = sec_service or SecService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        source_workbook_path: Path,
        custom_run_mapping: CustomRunMapping,
        workbook_structure: WorkbookStructure,
        company_facts: dict,
        filings_manifest: dict,
    ) -> tuple[ProvenanceReport, str, str, DecisionLogEntry]:
        provenance_entries: list[CellProvenance] = []

        for mapping in custom_run_mapping.entries:
            cell_ref = self.workbook_service.make_cell_ref(mapping.worksheet, mapping.cell)
            entry = CellProvenance(
                cell_ref=cell_ref,
                worksheet=mapping.worksheet,
                cell=mapping.cell,
                concept=mapping.concept,
                period=mapping.period,
            )

            if self.workbook_service.cell_contains_formula(
                workbook_structure, mapping.worksheet, mapping.cell
            ):
                entry.status = "skipped_formula"
                entry.failure_reason = "Cell contains a formula and was not overwritten."
                provenance_entries.append(entry)
                continue

            fact = self.sec_service.find_fact(
                company_facts,
                mapping.concept,
                mapping.period,
                mapping.xbrl_tag,
            )
            if fact is None:
                entry.status = "unfilled"
                entry.failure_reason = (
                    f"No SEC XBRL fact found for concept '{mapping.concept}' "
                    f"and period '{mapping.period}'."
                )
                provenance_entries.append(entry)
                continue

            filing_meta = self._resolve_filing(filings_manifest, fact)
            entry.value = fact.value
            entry.status = "filled"
            entry.xbrl_tag = f"{fact.taxonomy}:{fact.tag}"
            entry.source_document = filing_meta.get("document_url")
            entry.filing_type = fact.form or filing_meta.get("filing_type")
            entry.filing_year = fact.fiscal_year or filing_meta.get("fiscal_year")
            entry.filing_date = fact.filed or filing_meta.get("filing_date")
            entry.accession_number = fact.accession_number or filing_meta.get("accession_number")
            entry.confidence = self._confidence_score(fact, mapping.period)
            entry.reasoning = (
                f"Mapped '{mapping.concept}' ({mapping.period}) to XBRL tag "
                f"{fact.taxonomy}:{fact.tag} from {entry.filing_type} filed {entry.filing_date}."
            )
            provenance_entries.append(entry)

        provenance_report = ProvenanceReport(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            entries=provenance_entries,
        )

        completed_workbook_path = self.output_service.artifact_path(
            analysis.analysis_id,
            "completed_workbook.xlsx",
        )
        filled_count, blank_count, skipped_formula_count = self.workbook_service.write_values(
            source_workbook_path,
            completed_workbook_path,
            provenance_entries,
        )
        provenance_report.filled_count = filled_count
        provenance_report.blank_count = blank_count
        provenance_report.skipped_formula_count = skipped_formula_count

        provenance_path = self.output_service.write_json(
            analysis.analysis_id,
            "provenance_report.json",
            provenance_report,
        )
        workbook_path = self.output_service.relative_path(
            analysis.analysis_id,
            "completed_workbook.xlsx",
        )

        log_entry = DecisionLogEntry(
            agent="Workbook Completion Agent",
            action="fill_workbook",
            detail=(
                f"Filled {filled_count} cells, left {blank_count} blank, "
                f"preserved {skipped_formula_count} formula cells."
            ),
            confidence=round(filled_count / max(len(custom_run_mapping.entries), 1), 2),
            citations=[workbook_path, provenance_path],
        )
        return provenance_report, workbook_path, provenance_path, log_entry

    @staticmethod
    def _resolve_filing(filings_manifest: dict, fact: XbrlFact) -> dict:
        selected = filings_manifest.get("selected_filings", [])
        if fact.accession_number:
            for filing in selected:
                if filing.get("accession_number") == fact.accession_number:
                    return filing
        for filing in selected:
            if filing.get("filing_type") == fact.form:
                return filing
        return selected[0] if selected else {}

    @staticmethod
    def _confidence_score(fact: XbrlFact, period: str) -> float:
        score = 0.75
        if fact.fiscal_year and str(fact.fiscal_year) in period:
            score += 0.1
        if fact.fiscal_period and fact.fiscal_period in period.upper():
            score += 0.1
        if fact.form in {"10-K", "10-Q"}:
            score += 0.05
        return min(score, 0.99)
