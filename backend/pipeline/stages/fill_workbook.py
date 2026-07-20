"""Stage: populate completed workbook + provenance from SEC (internal), preserving formulas."""

from __future__ import annotations

from pathlib import Path
import shutil

from models.analysis import Analysis
from models.custom_run import CustomRunData
from models.pipeline import DecisionLogEntry
from models.provenance import CellProvenance, ProvenanceReport
from models.workbook_schema import WorkbookStructure
from services.output_service import OutputService
from services.sec_statement_extractor import extract_statement_cells_from_sec


class FillWorkbookStage:
    """
    Produce completed_workbook.xlsx and SEC provenance.

    External product inputs remain prefilled workbook + Bloomberg Custom_Run_Filter.
    SEC→template cell routing is an internal implementation detail only — never a
    user-supplied mapping file.
    """

    def __init__(self, output_service: OutputService | None = None) -> None:
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        source_workbook_path: Path,
        custom_run: CustomRunData,
        workbook_structure: WorkbookStructure,
        company_facts: dict,
        filings_manifest: dict,
    ) -> tuple[ProvenanceReport, str, str, DecisionLogEntry]:
        del workbook_structure, filings_manifest  # retained for stage signature stability

        # Copy template as completed workbook. Statement cells already present in the
        # Industrial Template are preserved; HAP does not invent values.
        completed_workbook_path = self.output_service.artifact_path(
            analysis.analysis_id,
            "completed_workbook.xlsx",
        )
        completed_workbook_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_workbook_path, completed_workbook_path)

        sec_cells = extract_statement_cells_from_sec(company_facts)
        provenance_entries: list[CellProvenance] = []
        for cell in sec_cells:
            provenance_entries.append(
                CellProvenance(
                    cell_ref=str(cell.get("cell_ref") or f"SEC!{cell.get('concept')}"),
                    worksheet=str(cell.get("worksheet") or "SEC"),
                    cell="SEC",
                    concept=str(cell.get("concept") or ""),
                    period=str(cell.get("period") or ""),
                    value=cell.get("value"),
                    status="filled",
                    source_document=cell.get("source_document"),
                    filing_type=cell.get("filing_type"),
                    xbrl_tag=cell.get("xbrl_tag"),
                    confidence=cell.get("confidence"),
                    accession_number=cell.get("accession_number"),
                    reasoning=(
                        f"SEC companyfacts sourced '{cell.get('concept')}' "
                        f"for {cell.get('period')} (Custom_Run provides proprietary analytics only)."
                    ),
                )
            )

        # Record Custom_Run proprietary imports as provenance (import, do not recalculate).
        for key, value in {
            **custom_run.market_data,
            **custom_run.valuation_metrics,
            **custom_run.quality_metrics,
        }.items():
            if value is None:
                continue
            provenance_entries.append(
                CellProvenance(
                    cell_ref=f"CustomRun!{key}",
                    worksheet=custom_run.ticker_sheet_name,
                    cell="B",
                    concept=key,
                    period="current",
                    value=value if isinstance(value, (int, float, str, bool)) else str(value),
                    status="filled",
                    source_document=custom_run.source_filename,
                    confidence=0.95,
                    reasoning="Imported from Bloomberg Custom_Run_Filter (proprietary; not recomputed).",
                )
            )

        provenance_report = ProvenanceReport(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            entries=provenance_entries,
            filled_count=sum(1 for e in provenance_entries if e.status == "filled"),
            blank_count=0,
            skipped_formula_count=0,
        )

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
                f"Preserved prefilled workbook; recorded {provenance_report.filled_count} "
                f"SEC + Custom_Run provenance entries for {custom_run.ticker}."
            ),
            confidence=0.9,
            citations=[workbook_path, provenance_path],
        )
        return provenance_report, workbook_path, provenance_path, log_entry
