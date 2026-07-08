"""Stage: validate completed workbook values and generate discrepancy report."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.custom_run import CustomRunMapping
from models.pipeline import DecisionLogEntry
from models.provenance import ProvenanceReport
from models.validation import DiscrepancyReport
from services.output_service import OutputService
from services.validation_service import ValidationService


class ValidateWorkbookStage:
    """Validate every filled value and produce a discrepancy report."""

    def __init__(
        self,
        validation_service: ValidationService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.validation_service = validation_service or ValidationService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run_mapping: CustomRunMapping,
        provenance_report: ProvenanceReport,
        completed_workbook_path: Path,
    ) -> tuple[DiscrepancyReport, str, str, DecisionLogEntry]:
        discrepancy_report = self.validation_service.validate(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            custom_run_entries=custom_run_mapping.entries,
            provenance_report=provenance_report,
            completed_workbook_path=completed_workbook_path,
        )

        discrepancy_path = self.output_service.write_json(
            analysis.analysis_id,
            "discrepancy_report.json",
            discrepancy_report,
        )
        validation_path = self.output_service.write_json(
            analysis.analysis_id,
            "validation_report.json",
            discrepancy_report,
        )

        log_entry = DecisionLogEntry(
            agent="Workbook Validation Agent",
            action="validate_workbook",
            detail=discrepancy_report.summary,
            confidence=round(
                discrepancy_report.pass_count / max(len(discrepancy_report.checks), 1),
                2,
            ),
            citations=[validation_path, discrepancy_path],
        )
        return discrepancy_report, validation_path, discrepancy_path, log_entry
