"""Stage: validate custom_run_filter and produce a validation report."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.custom_run import CustomRunMapping, CustomRunValidationReport
from models.pipeline import DecisionLogEntry
from models.workbook_schema import WorkbookStructure
from services.custom_run_service import CustomRunParseError, CustomRunService
from services.output_service import OutputService


class ValidateCustomRunStage:
    """
    Parse and validate the custom_run filter.

    Produces mapping + validation report artifacts. Does not populate the
    workbook template.
    """

    def __init__(
        self,
        custom_run_service: CustomRunService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.custom_run_service = custom_run_service or CustomRunService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run_path: Path,
        structure: WorkbookStructure,
    ) -> tuple[CustomRunMapping, CustomRunValidationReport, str, str, DecisionLogEntry]:
        if analysis.files.custom_run_filter is None:
            raise CustomRunParseError("custom_run_filter is required to run the HAP pipeline.")

        original_filename = analysis.files.custom_run_filter.filename
        mapping = self.custom_run_service.parse(custom_run_path, original_filename)
        report = self.custom_run_service.validate(
            mapping,
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            structure=structure,
        )

        mapping_path = self.output_service.write_json(
            analysis.analysis_id,
            "custom_run_mapping.json",
            mapping,
        )
        report_path = self.output_service.write_json(
            analysis.analysis_id,
            "custom_run_validation_report.json",
            report,
        )

        if not report.is_valid:
            fail_messages = [check.message for check in report.checks if check.status == "fail"]
            detail = "; ".join(fail_messages) if fail_messages else report.summary
            raise CustomRunParseError(detail)

        log_entry = DecisionLogEntry(
            agent="Workbook Validation Agent",
            action="validate_custom_run_filter",
            detail=(
                f"Validated {mapping.entry_count} mappings from {original_filename} "
                f"({report.pass_count} pass, {report.warn_count} warn, {report.fail_count} fail). "
                "Template was not populated."
            ),
            confidence=1.0 if report.warn_count == 0 else 0.8,
            citations=[mapping_path, report_path],
        )
        return mapping, report, mapping_path, report_path, log_entry
