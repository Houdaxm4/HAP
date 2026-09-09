"""Stage: completion planning + M4 fill (only FILL decisions write)."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.completion import CompletionReport
from models.custom_run import CustomRunData
from models.pipeline import DecisionLogEntry
from models.provenance import CellProvenance, ProvenanceReport
from models.workbook_schema import WorkbookStructure
from services.completion_service import CompletionService
from services.current_data_refresh_service import CurrentDataRefreshService
from services.excel_fill_service import ExcelFillService
from services.file_service import FileService
from services.output_service import OutputService
from services.quarterly_margin_service import QuarterlyMarginService
from services.quarterly_presentation_service import QuarterlyPresentationService
from services.sec_statement_extractor import extract_statement_cells_from_sec
from workbook_mapping.engine import WriteIntentReport
from services.completion_scope import normalize_analysis_type, AnalysisTypeMode


class FillWorkbookStage:
    """
    Phase A completion + M4 apply:

    1. Inspect workbook vs M3 intents → completion_report.json
    2. Apply only FILL decisions to a copy of the upload
    3. Preserve ALREADY_PRESENT prefilled values (no rewrite)
    """

    def __init__(
        self,
        output_service: OutputService | None = None,
        excel_fill_service: ExcelFillService | None = None,
        completion_service: CompletionService | None = None,
    ) -> None:
        self.output_service = output_service or OutputService()
        self.excel_fill_service = excel_fill_service or ExcelFillService()
        self.completion_service = completion_service or CompletionService()
        self.quarterly_presentation = QuarterlyPresentationService()
        self.current_data_refresh = CurrentDataRefreshService()
        self.quarterly_margins = QuarterlyMarginService()
        self.file_service = FileService()

    def run(
        self,
        analysis: Analysis,
        source_workbook_path: Path,
        custom_run: CustomRunData,
        workbook_structure: WorkbookStructure,
        company_facts: dict,
        filings_manifest: dict,
        write_intents_path: str | None = None,
    ) -> tuple[ProvenanceReport, CompletionReport, str, str, str, str, DecisionLogEntry]:
        del workbook_structure, filings_manifest  # retained for signature stability

        completed_workbook_path = self.output_service.artifact_path(
            analysis.analysis_id,
            "completed_workbook.xlsx",
        )

        intent_report = self._load_intent_report(analysis, write_intents_path)
        completion_report, fill_intents = self.completion_service.plan(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            analysis_type=analysis.analysis_type or "new_company",
            source_workbook_path=source_workbook_path,
            intent_report=intent_report,
            target_fiscal_year=getattr(analysis, "target_fiscal_year", None),
        )
        completion_path = self.output_service.write_json(
            analysis.analysis_id,
            "completion_report.json",
            completion_report,
        )
        # Persist the filtered intents actually used for fill (audit trail).
        self.output_service.write_json(
            analysis.analysis_id,
            "completion_fill_intents.json",
            fill_intents,
        )

        excel_provenance, cell_diff, written, runtime_skip, runtime_block = (
            self.excel_fill_service.apply_write_intents(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                source_workbook_path=source_workbook_path,
                destination_workbook_path=completed_workbook_path,
                intent_report=fill_intents,
            )
        )

        q_presentation_note = ""
        mode = normalize_analysis_type(analysis.analysis_type or "new_company")
        if mode == AnalysisTypeMode.QUARTERLY_UPDATE:
            try:
                crf_path = self.file_service.get_custom_run_filter_path(analysis)
            except Exception:  # noqa: BLE001
                crf_path = None
            refresh = self.current_data_refresh.apply(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
                custom_run_path=crf_path,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "current_data_refresh_report.json",
                refresh,
            )
            q_report = self.quarterly_presentation.plan_and_apply(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                source_workbook_path=source_workbook_path,
                destination_workbook_path=completed_workbook_path,
                company_facts=company_facts,
                already_copied=True,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "quarterly_presentation_report.json",
                q_report,
            )
            margin_report = self.quarterly_margins.apply(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "quarterly_margin_report.json",
                margin_report,
            )
            q_presentation_note = f"; {q_report.summary}; {refresh.summary}; {margin_report.summary}"
            completion_report.quarterly_health = {
                **(completion_report.quarterly_health or {}),
                "presentation_summary": q_report.summary,
                "presentation_decisions": {
                    s.statement.value: s.decision.value for s in q_report.statements
                },
                "current_data_refresh": refresh.summary,
                "margins": margin_report.summary,
            }
            # Refresh completion artifact with presentation annotations.
            self.output_service.write_json(
                analysis.analysis_id,
                "completion_report.json",
                completion_report,
            )

        provenance_entries: list[CellProvenance] = list(excel_provenance)
        for cell in extract_statement_cells_from_sec(company_facts):
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

        filled_count = sum(1 for e in provenance_entries if e.status == "filled")
        provenance_report = ProvenanceReport(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            entries=provenance_entries,
            filled_count=filled_count,
            blank_count=sum(1 for e in excel_provenance if e.status == "blank"),
            skipped_formula_count=sum(
                1 for e in excel_provenance if e.status == "skipped_formula"
            ),
        )

        cell_diff_path = self.output_service.write_json(
            analysis.analysis_id,
            "cell_diff_report.json",
            cell_diff,
        )
        provenance_path = self.output_service.write_json(
            analysis.analysis_id,
            "provenance_report.json",
            provenance_report,
        )
        workbook_rel = self.output_service.relative_path(
            analysis.analysis_id,
            "completed_workbook.xlsx",
        )
        log_entry = DecisionLogEntry(
            agent="Workbook Completion Agent",
            action="fill_workbook",
            detail=(
                f"Completion+M4 for {analysis.ticker} "
                f"[{completion_report.normalized_analysis_type or analysis.analysis_type}]: "
                f"FILL={completion_report.fill_count}, "
                f"ALREADY_PRESENT={completion_report.already_present_count}, "
                f"OUT_OF_SCOPE={completion_report.out_of_scope_count}, "
                f"MISSING_SOURCE={completion_report.missing_source_count}, "
                f"BLOCKED={completion_report.blocked_count}, "
                f"SEC_Q_FALLBACK={completion_report.sec_quarterly_fallback_count}; "
                f"excel_wrote={written}, cell_diff_changed={cell_diff.changed_count} "
                f"(upload unchanged){q_presentation_note}."
            ),
            confidence=0.9,
            citations=[workbook_rel, provenance_path, cell_diff_path, completion_path],
        )
        return (
            provenance_report,
            completion_report,
            workbook_rel,
            provenance_path,
            cell_diff_path,
            completion_path,
            log_entry,
        )

    def _load_intent_report(
        self,
        analysis: Analysis,
        write_intents_path: str | None,
    ) -> WriteIntentReport:
        """Load M3 artifact; do not recompute mappings."""
        filename = "write_intents.json"
        if write_intents_path:
            name = Path(write_intents_path).name
            if name:
                filename = name
        raw = self.output_service.read_json(analysis.analysis_id, filename)
        return WriteIntentReport.model_validate(raw)
