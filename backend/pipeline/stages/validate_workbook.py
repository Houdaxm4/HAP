"""Stage: validate Custom_Run_Filter (product spec) and SEC provenance integrity."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.custom_run import CustomRunData
from models.pipeline import DecisionLogEntry
from models.provenance import ProvenanceReport
from models.validation import DiscrepancyReport, ValidationCheck
from services.custom_run_validation import CustomRunValidationService
from services.output_service import OutputService


class ValidateWorkbookStage:
    """Validate Bloomberg Custom_Run structure and basic provenance integrity."""

    def __init__(
        self,
        custom_run_validation: CustomRunValidationService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.custom_run_validation = custom_run_validation or CustomRunValidationService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run: CustomRunData,
        provenance_report: ProvenanceReport,
        completed_workbook_path: Path,
    ) -> tuple[DiscrepancyReport, str, str, DecisionLogEntry]:
        del completed_workbook_path  # presence asserted by orchestrator / fill stage

        report = self.custom_run_validation.validate(analysis.analysis_id, custom_run)

        # Append light provenance integrity checks (SEC facts recorded).
        sec_filled = [
            entry
            for entry in provenance_report.entries
            if entry.worksheet == "SEC" and entry.status == "filled"
        ]
        report.checks.append(
            ValidationCheck(
                cell_ref="SEC!coverage",
                worksheet="SEC",
                cell="-",
                concept="sec_statement_facts",
                period="multi",
                check_type="value_match" if sec_filled else "missing_value",
                status="pass" if len(sec_filled) >= 10 else "warn",
                message=(
                    f"Recorded {len(sec_filled)} SEC statement fact entries."
                    if sec_filled
                    else "No SEC statement facts were recorded."
                ),
            )
        )
        report.pass_count = sum(1 for c in report.checks if c.status == "pass")
        report.warn_count = sum(1 for c in report.checks if c.status == "warn")
        report.fail_count = sum(1 for c in report.checks if c.status == "fail")
        if report.fail_count:
            report.summary = (
                f"{report.fail_count} failed, {report.warn_count} warnings, "
                f"{report.pass_count} passed."
            )
        elif report.warn_count:
            report.summary = (
                f"Validation completed with {report.warn_count} warnings and "
                f"{report.pass_count} passed checks."
            )
        else:
            report.summary = f"All {report.pass_count} checks passed."

        discrepancy_path = self.output_service.write_json(
            analysis.analysis_id,
            "discrepancy_report.json",
            report,
        )
        validation_path = self.output_service.write_json(
            analysis.analysis_id,
            "validation_report.json",
            report,
        )
        log_entry = DecisionLogEntry(
            agent="Workbook Validation Agent",
            action="validate_workbook",
            detail=report.summary,
            confidence=round(report.pass_count / max(len(report.checks), 1), 2),
            citations=[validation_path, discrepancy_path],
        )
        return report, validation_path, discrepancy_path, log_entry
