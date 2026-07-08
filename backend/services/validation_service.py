"""Workbook validation and discrepancy reporting."""

from __future__ import annotations

from typing import Any

from models.custom_run import CustomRunEntry
from models.provenance import CellProvenance, ProvenanceReport
from models.validation import DiscrepancyReport, ValidationCheck
from services.workbook_service import WorkbookService


class ValidationService:
    """Validate populated workbook values against provenance and custom_run."""

    def __init__(self, workbook_service: WorkbookService | None = None) -> None:
        self.workbook_service = workbook_service or WorkbookService()

    def validate(
        self,
        analysis_id: str,
        ticker: str,
        custom_run_entries: list[CustomRunEntry],
        provenance_report: ProvenanceReport,
        completed_workbook_path: Any,
    ) -> DiscrepancyReport:
        """Run validation checks and build a discrepancy report."""
        provenance_by_ref = {entry.cell_ref: entry for entry in provenance_report.entries}
        checks: list[ValidationCheck] = []

        for mapping in custom_run_entries:
            cell_ref = self.workbook_service.make_cell_ref(mapping.worksheet, mapping.cell)
            provenance = provenance_by_ref.get(cell_ref)

            if provenance is None:
                checks.append(
                    ValidationCheck(
                        cell_ref=cell_ref,
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        concept=mapping.concept,
                        period=mapping.period,
                        check_type="missing_value",
                        status="fail",
                        message="No provenance record was generated for this mapping.",
                    )
                )
                continue

            if provenance.status == "skipped_formula":
                checks.append(
                    ValidationCheck(
                        cell_ref=cell_ref,
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        concept=mapping.concept,
                        period=mapping.period,
                        check_type="formula_preserved",
                        status="pass",
                        message="Formula cell was correctly preserved and not overwritten.",
                    )
                )
                continue

            if provenance.status != "filled" or provenance.value is None:
                checks.append(
                    ValidationCheck(
                        cell_ref=cell_ref,
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        concept=mapping.concept,
                        period=mapping.period,
                        check_type="unfilled",
                        status="warn",
                        message=provenance.failure_reason or "Value could not be sourced from SEC filings.",
                    )
                )
                continue

            actual_value = self.workbook_service.get_cell_value(
                completed_workbook_path,
                mapping.worksheet,
                mapping.cell,
            )
            if not self._values_match(provenance.value, actual_value):
                checks.append(
                    ValidationCheck(
                        cell_ref=cell_ref,
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        concept=mapping.concept,
                        period=mapping.period,
                        check_type="inconsistency",
                        status="fail",
                        expected_value=provenance.value,
                        actual_value=actual_value,
                        message="Completed workbook value does not match provenance record.",
                        source_document=provenance.source_document,
                        xbrl_tag=provenance.xbrl_tag,
                    )
                )
                continue

            confidence = provenance.confidence or 0.0
            status = "pass" if confidence >= 0.6 else "warn"
            message = "Value matches provenance and SEC source."
            if confidence < 0.6:
                message = "Value matches provenance but confidence is below threshold."

            if self._is_impossible_value(mapping.concept, provenance.value):
                checks.append(
                    ValidationCheck(
                        cell_ref=cell_ref,
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        concept=mapping.concept,
                        period=mapping.period,
                        check_type="impossible_value",
                        status="fail",
                        expected_value=provenance.value,
                        actual_value=actual_value,
                        message="Value failed plausibility checks.",
                        source_document=provenance.source_document,
                        xbrl_tag=provenance.xbrl_tag,
                    )
                )
                continue

            checks.append(
                ValidationCheck(
                    cell_ref=cell_ref,
                    worksheet=mapping.worksheet,
                    cell=mapping.cell,
                    concept=mapping.concept,
                    period=mapping.period,
                    check_type="value_match",
                    status=status,
                    expected_value=provenance.value,
                    actual_value=actual_value,
                    message=message,
                    source_document=provenance.source_document,
                    xbrl_tag=provenance.xbrl_tag,
                )
            )

        pass_count = sum(1 for check in checks if check.status == "pass")
        warn_count = sum(1 for check in checks if check.status == "warn")
        fail_count = sum(1 for check in checks if check.status == "fail")

        if fail_count:
            summary = f"{fail_count} failed, {warn_count} warnings, {pass_count} passed."
        elif warn_count:
            summary = f"Validation completed with {warn_count} warnings and {pass_count} passed checks."
        else:
            summary = f"All {pass_count} checks passed."

        return DiscrepancyReport(
            analysis_id=analysis_id,
            ticker=ticker,
            checks=checks,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
            summary=summary,
        )

    @staticmethod
    def _values_match(expected: Any, actual: Any) -> bool:
        if expected is None and actual is None:
            return True
        if expected is None or actual is None:
            return False
        try:
            return abs(float(expected) - float(actual)) <= max(1.0, abs(float(expected)) * 0.0001)
        except (TypeError, ValueError):
            return str(expected).strip() == str(actual).strip()

    @staticmethod
    def _is_impossible_value(concept: str, value: Any) -> bool:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        lowered = concept.lower()
        if "shares" in lowered or "eps" in lowered or "per share" in lowered:
            return numeric < 0
        if numeric < 0 and any(token in lowered for token in ("revenue", "assets", "cash flow")):
            return True
        return False
