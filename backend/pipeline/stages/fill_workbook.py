"""Stage: populate workbook cells from CompanyFinancialModel via internal mapping."""

from __future__ import annotations

from pathlib import Path

from ingestion.models.company_financial_model import CompanyFinancialModel
from ingestion.prefilled_workbook_mapper import InternalFillTarget, PrefilledWorkbookMapper
from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from models.provenance import CellProvenance, ProvenanceReport
from models.workbook_schema import WorkbookStructure
from services.output_service import OutputService
from services.workbook_service import WorkbookService


class FillWorkbookStage:
    """Fill prefilled workbook using internally derived fill targets."""

    def __init__(
        self,
        workbook_service: WorkbookService | None = None,
        mapper: PrefilledWorkbookMapper | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.workbook_service = workbook_service or WorkbookService()
        self.mapper = mapper or PrefilledWorkbookMapper(self.workbook_service)
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        source_workbook_path: Path,
        financial_model: CompanyFinancialModel,
        workbook_structure: WorkbookStructure,
        filings_manifest: dict,
    ) -> tuple[ProvenanceReport, str, str, DecisionLogEntry]:
        fill_targets = self.mapper.build_fill_plan(workbook_structure, financial_model)
        provenance_entries = self._to_provenance(fill_targets, workbook_structure, filings_manifest)

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
                f"Filled {filled_count} cells from CompanyFinancialModel "
                f"({len(fill_targets)} internal targets), "
                f"preserved {skipped_formula_count} formula cells."
            ),
            confidence=round(filled_count / max(len(fill_targets), 1), 2),
            citations=[workbook_path, provenance_path],
        )
        return provenance_report, workbook_path, provenance_path, log_entry

    def _to_provenance(
        self,
        targets: list[InternalFillTarget],
        structure: WorkbookStructure,
        filings_manifest: dict,
    ) -> list[CellProvenance]:
        entries: list[CellProvenance] = []
        default_filing = (filings_manifest.get("selected_filings") or [{}])[0]

        for target in targets:
            cell_ref = self.workbook_service.make_cell_ref(target.worksheet, target.cell)
            entry = CellProvenance(
                cell_ref=cell_ref,
                worksheet=target.worksheet,
                cell=target.cell,
                concept=target.concept,
                period=target.period,
                value=target.value,
                status=target.status,
                xbrl_tag=target.xbrl_tag,
                source_document=target.source_document or default_filing.get("document_url"),
                filing_type=target.filing_type or default_filing.get("filing_type"),
                filing_date=target.filing_date or default_filing.get("filing_date"),
                accession_number=target.accession_number or default_filing.get("accession_number"),
                confidence=target.confidence,
                reasoning=target.reasoning,
                failure_reason=target.failure_reason,
            )

            if self.workbook_service.cell_contains_formula(
                structure, target.worksheet, target.cell
            ):
                entry.status = "skipped_formula"
                entry.failure_reason = "Cell contains a formula and was not overwritten."
            elif target.value is None:
                entry.status = "unfilled"
                entry.failure_reason = target.failure_reason or "No value available."

            entries.append(entry)
        return entries
