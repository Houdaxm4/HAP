"""Stage: validate completed workbook and generate provenance/validation reports."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from models.analysis import Analysis
from models.custom_run import CustomRunMapping, CustomRunValidationReport
from models.pipeline import DecisionLogEntry
from models.provenance import ProvenanceReport
from models.validation import DiscrepancyReport, ValidationReport
from models.workbook_schema import WorkbookStructure
from services.output_service import OutputService
from services.validation_service import ValidationService

logger = logging.getLogger(__name__)


class ValidateWorkbookStage:
    """Validate every filled value and produce validation + discrepancy reports."""

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
        source_workbook_path: Path | None = None,
        workbook_structure: WorkbookStructure | None = None,
        custom_run_validation_report: CustomRunValidationReport | None = None,
        financial_statements: dict[str, Any] | None = None,
    ) -> tuple[ValidationReport, DiscrepancyReport, str, str, DecisionLogEntry]:
        validation_report = self.validation_service.validate_trusted_model(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            custom_run_mapping=custom_run_mapping,
            provenance_report=provenance_report,
            completed_workbook_path=completed_workbook_path,
            source_workbook_path=source_workbook_path,
            workbook_structure=workbook_structure,
            custom_run_validation_report=custom_run_validation_report,
            financial_statements=financial_statements,
            original_sheet_names=(
                list(workbook_structure.worksheet_names) if workbook_structure else None
            ),
        )

        discrepancy_report = self.validation_service.validate(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            custom_run_entries=custom_run_mapping.entries,
            provenance_report=provenance_report,
            completed_workbook_path=completed_workbook_path,
        )

        validation_path = self.output_service.write_json(
            analysis.analysis_id,
            "validation_report.json",
            validation_report,
        )
        discrepancy_path = self.output_service.write_json(
            analysis.analysis_id,
            "discrepancy_report.json",
            discrepancy_report,
        )

        log_entry = DecisionLogEntry(
            agent="Workbook Validation Agent",
            action="validate_workbook",
            detail=validation_report.summary,
            confidence=1.0 if validation_report.overall_status != "failed" else 0.0,
            citations=[validation_path, discrepancy_path],
        )
        logger.info(
            "Validation stage for %s: %s",
            analysis.analysis_id,
            validation_report.overall_status,
        )
        return validation_report, discrepancy_report, validation_path, discrepancy_path, log_entry
