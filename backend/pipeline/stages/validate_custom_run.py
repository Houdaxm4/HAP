"""Stage: validate Bloomberg Custom_Run_Filter workbook structure and content."""

from __future__ import annotations

from ingestion.custom_run_validator import CustomRunValidationError, CustomRunValidator
from ingestion.models.custom_run_data import CustomRunData, CustomRunValidationReport
from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from services.output_service import OutputService


class ValidateCustomRunStage:
    """Validate CustomRunData against the HAP v1 ingestion specification."""

    def __init__(
        self,
        validator: CustomRunValidator | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.validator = validator or CustomRunValidator()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run_data: CustomRunData,
    ) -> tuple[CustomRunValidationReport, str, DecisionLogEntry]:
        report = self.validator.validate_or_raise(
            custom_run_data,
            expected_ticker=analysis.ticker,
        )
        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "custom_run_validation.json",
            report,
        )
        log_entry = DecisionLogEntry(
            agent="Workbook Validation Agent",
            action="validate_custom_run",
            detail=report.summary,
            confidence=round(report.pass_count / max(len(report.checks), 1), 2),
            citations=[artifact_path],
        )
        return report, artifact_path, log_entry
