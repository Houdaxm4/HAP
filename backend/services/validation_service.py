"""Workbook validation and discrepancy reporting for the trusted financial model."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from models.custom_run import CustomRunEntry, CustomRunMapping, CustomRunValidationReport
from models.provenance import CellProvenance, ProvenanceReport
from models.validation import (
    DiscrepancyReport,
    ValidationCheck,
    ValidationIssue,
    ValidationOverallStatus,
    ValidationReport,
)
from models.workbook_schema import WorkbookStructure
from services.workbook_service import WorkbookService

logger = logging.getLogger(__name__)


class ValidationThresholds:
    """Configurable plausibility and reconciliation thresholds."""

    def __init__(
        self,
        balance_sheet_tolerance_pct: float = 0.01,
        cash_reconcile_tolerance_pct: float = 0.01,
        net_income_tolerance_pct: float = 0.02,
        extreme_tax_rate_low: float = -0.05,
        extreme_tax_rate_high: float = 0.55,
        extreme_margin_low: float = -0.5,
        extreme_margin_high: float = 0.8,
        extreme_roic_low: float = -0.5,
        extreme_roic_high: float = 1.0,
        discontinuity_pct: float = 0.75,
        scale_mismatch_ratio: float = 80.0,
    ) -> None:
        self.balance_sheet_tolerance_pct = balance_sheet_tolerance_pct
        self.cash_reconcile_tolerance_pct = cash_reconcile_tolerance_pct
        self.net_income_tolerance_pct = net_income_tolerance_pct
        self.extreme_tax_rate_low = extreme_tax_rate_low
        self.extreme_tax_rate_high = extreme_tax_rate_high
        self.extreme_margin_low = extreme_margin_low
        self.extreme_margin_high = extreme_margin_high
        self.extreme_roic_low = extreme_roic_low
        self.extreme_roic_high = extreme_roic_high
        self.discontinuity_pct = discontinuity_pct
        self.scale_mismatch_ratio = scale_mismatch_ratio


class ValidationService:
    """Validate completed workbooks, provenance, and financial integrity."""

    REQUIRED_WORKSHEETS = ("Income Statement", "Balance Sheet")

    def __init__(
        self,
        workbook_service: WorkbookService | None = None,
        thresholds: ValidationThresholds | None = None,
    ) -> None:
        self.workbook_service = workbook_service or WorkbookService()
        self.thresholds = thresholds or ValidationThresholds()

    def validate_trusted_model(
        self,
        analysis_id: str,
        ticker: str,
        custom_run_mapping: CustomRunMapping,
        provenance_report: ProvenanceReport,
        completed_workbook_path: Path,
        source_workbook_path: Path | None = None,
        workbook_structure: WorkbookStructure | None = None,
        custom_run_validation_report: CustomRunValidationReport | None = None,
        financial_statements: dict[str, Any] | None = None,
        original_sheet_names: list[str] | None = None,
    ) -> ValidationReport:
        """
        Run the full trusted-model validation suite.

        Produces critical / warning / informational issues and an overall status.
        """
        issues: list[ValidationIssue] = []
        checks_passed = 0
        unresolved_fields: list[str] = []

        # --- Workbook integrity ---
        integrity_passed, integrity_issues = self._check_workbook_integrity(
            completed_workbook_path=completed_workbook_path,
            source_workbook_path=source_workbook_path,
            workbook_structure=workbook_structure,
            custom_run_mapping=custom_run_mapping,
            provenance_report=provenance_report,
            original_sheet_names=original_sheet_names,
        )
        issues.extend(integrity_issues)
        checks_passed += integrity_passed

        # --- custom_run_filter structural failures escalate to critical ---
        if custom_run_validation_report is not None:
            passed, cr_issues = self._check_custom_run_report(custom_run_validation_report)
            issues.extend(cr_issues)
            checks_passed += passed

        # --- Provenance completeness & write rules ---
        passed, prov_issues, unresolved = self._check_provenance_rules(
            custom_run_mapping=custom_run_mapping,
            provenance_report=provenance_report,
            completed_workbook_path=completed_workbook_path,
        )
        issues.extend(prov_issues)
        unresolved_fields.extend(unresolved)
        checks_passed += passed

        # --- Data-source reconciliation ---
        passed, recon_issues = self._check_source_reconciliation(provenance_report)
        issues.extend(recon_issues)
        checks_passed += passed

        # --- Financial statement checks (from extracted statements when available) ---
        if financial_statements:
            passed, fin_issues = self._check_financial_statements(financial_statements)
            issues.extend(fin_issues)
            checks_passed += passed

        # --- Plausibility ---
        passed, plaus_issues = self._check_plausibility(provenance_report)
        issues.extend(plaus_issues)
        checks_passed += passed

        critical_count = sum(1 for i in issues if i.severity == "critical")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        informational_count = sum(1 for i in issues if i.severity == "informational")
        total_checks = checks_passed + len(issues)

        overall_status: ValidationOverallStatus
        if critical_count > 0:
            overall_status = "failed"
            summary = (
                f"Validation failed with {critical_count} critical issue(s), "
                f"{warning_count} warning(s), {informational_count} informational."
            )
        elif warning_count > 0:
            overall_status = "passed_with_warnings"
            summary = (
                f"Validation passed with warnings: {warning_count} warning(s), "
                f"{informational_count} informational. Analyst review required."
            )
        else:
            overall_status = "passed"
            summary = (
                f"All checks passed ({checks_passed} passed, "
                f"{informational_count} informational)."
            )

        report = ValidationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            issues=issues,
            total_checks=total_checks,
            checks_passed=checks_passed,
            critical_count=critical_count,
            warning_count=warning_count,
            informational_count=informational_count,
            unresolved_fields=sorted(set(unresolved_fields)),
            overall_status=overall_status,
            summary=summary,
        )
        logger.info(
            "Validation complete for %s: status=%s critical=%s warnings=%s",
            analysis_id,
            overall_status,
            critical_count,
            warning_count,
        )
        return report

    def validate(
        self,
        analysis_id: str,
        ticker: str,
        custom_run_entries: list[CustomRunEntry],
        provenance_report: ProvenanceReport,
        completed_workbook_path: Any,
    ) -> DiscrepancyReport:
        """Legacy cell-level discrepancy report (backward compatible)."""
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

            if provenance.status in {"unfilled", "unresolved"} or (
                provenance.status != "filled" and provenance.value is None
            ):
                checks.append(
                    ValidationCheck(
                        cell_ref=cell_ref,
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        concept=mapping.concept,
                        period=mapping.period,
                        check_type="unfilled",
                        status="warn",
                        message=provenance.failure_reason
                        or "Value could not be sourced from SEC filings.",
                    )
                )
                continue

            actual_value = self.workbook_service.get_cell_value(
                completed_workbook_path,
                mapping.worksheet,
                mapping.cell,
            )
            if provenance.status == "preserved_existing":
                checks.append(
                    ValidationCheck(
                        cell_ref=cell_ref,
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        concept=mapping.concept,
                        period=mapping.period,
                        check_type="value_match",
                        status="warn",
                        expected_value=provenance.proposed_value,
                        actual_value=actual_value,
                        message="Existing populated value preserved; filing value recorded as conflict.",
                        source_document=provenance.source_document,
                        xbrl_tag=provenance.xbrl_tag,
                    )
                )
                continue

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

    def _check_workbook_integrity(
        self,
        completed_workbook_path: Path,
        source_workbook_path: Path | None,
        workbook_structure: WorkbookStructure | None,
        custom_run_mapping: CustomRunMapping,
        provenance_report: ProvenanceReport,
        original_sheet_names: list[str] | None,
    ) -> tuple[int, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        passed = 0

        try:
            completed_structure = self.workbook_service.parse_structure(
                completed_workbook_path,
                "completed_workbook.xlsx",
            )
            passed += 1
        except Exception as exc:  # noqa: BLE001 — surface as critical validation issue
            issues.append(
                ValidationIssue(
                    code="WORKBOOK_CORRUPT",
                    severity="critical",
                    message=f"Completed workbook cannot be opened: {exc}",
                    rule="workbook_can_be_opened",
                    suggested_analyst_action="Re-run workbook completion or inspect the source template.",
                    blocks_pipeline=True,
                )
            )
            return passed, issues

        expected_names = original_sheet_names
        if expected_names is None and workbook_structure is not None:
            expected_names = list(workbook_structure.worksheet_names)

        if expected_names:
            missing = [n for n in expected_names if n not in completed_structure.worksheet_names]
            extra_deleted = [
                n for n in expected_names if n not in completed_structure.worksheet_names
            ]
            if missing or extra_deleted:
                issues.append(
                    ValidationIssue(
                        code="REQUIRED_WORKSHEET_MISSING",
                        severity="critical",
                        message=f"Required worksheet(s) missing from completed workbook: {missing}",
                        rule="required_worksheets_exist",
                        expected_value=expected_names,
                        actual_value=completed_structure.worksheet_names,
                        suggested_analyst_action="Restore the original workbook template and re-run.",
                        blocks_pipeline=True,
                    )
                )
            else:
                passed += 1

            # Detect unexpected deletions relative to source structure
            if set(completed_structure.worksheet_names) != set(expected_names):
                deleted = sorted(set(expected_names) - set(completed_structure.worksheet_names))
                if deleted:
                    issues.append(
                        ValidationIssue(
                            code="WORKSHEET_DELETED",
                            severity="critical",
                            message=f"Unexpected worksheet deletion: {deleted}",
                            rule="no_unexpected_worksheet_deletion",
                            blocks_pipeline=True,
                            suggested_analyst_action="Do not delete worksheets during completion.",
                        )
                    )
                else:
                    # Added sheets are informational only
                    added = sorted(set(completed_structure.worksheet_names) - set(expected_names))
                    if added:
                        issues.append(
                            ValidationIssue(
                                code="WORKSHEET_ADDED",
                                severity="informational",
                                message=f"Additional worksheet(s) present: {added}",
                                rule="worksheet_set_stable",
                            )
                        )
                    else:
                        passed += 1
            else:
                passed += 1

        # Required mapped worksheets from custom_run
        mapped_sheets = {e.worksheet for e in custom_run_mapping.entries}
        missing_mapped = [s for s in mapped_sheets if s not in completed_structure.worksheet_names]
        if missing_mapped:
            issues.append(
                ValidationIssue(
                    code="MAPPED_WORKSHEET_MISSING",
                    severity="critical",
                    message=f"Mapped worksheet(s) missing: {missing_mapped}",
                    rule="mapped_worksheets_present",
                    blocks_pipeline=True,
                    suggested_analyst_action="Ensure custom_run_filter worksheets exist in the template.",
                )
            )
        else:
            passed += 1

        # Formula preservation: every skipped_formula provenance must still be a formula
        for entry in provenance_report.entries:
            if entry.status != "skipped_formula":
                continue
            if not self.workbook_service.cell_contains_formula(
                completed_structure, entry.worksheet, entry.cell
            ):
                # Also check raw workbook (structure may omit some cells)
                raw = self.workbook_service.get_cell_formula(
                    completed_workbook_path, entry.worksheet, entry.cell
                )
                if raw is None:
                    issues.append(
                        ValidationIssue(
                            code="FORMULA_OVERWRITTEN",
                            severity="critical",
                            message=f"Formula cell {entry.cell_ref} was overwritten.",
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            rule="never_overwrite_formula",
                            blocks_pipeline=True,
                            suggested_analyst_action="Restore the formula from the source workbook.",
                        )
                    )
                else:
                    passed += 1
            else:
                passed += 1

        # Source vs completed formula count sanity
        if source_workbook_path is not None and source_workbook_path.exists():
            try:
                source_structure = self.workbook_service.parse_structure(
                    source_workbook_path, "source.xlsx"
                )
                if completed_structure.formula_count < source_structure.formula_count:
                    issues.append(
                        ValidationIssue(
                            code="FORMULA_COUNT_DECREASED",
                            severity="critical",
                            message=(
                                f"Formula count decreased from {source_structure.formula_count} "
                                f"to {completed_structure.formula_count}."
                            ),
                            rule="formulas_remain_formulas",
                            expected_value=source_structure.formula_count,
                            actual_value=completed_structure.formula_count,
                            blocks_pipeline=True,
                            suggested_analyst_action="Investigate overwritten formula cells.",
                        )
                    )
                else:
                    passed += 1
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    ValidationIssue(
                        code="SOURCE_WORKBOOK_UNREADABLE",
                        severity="warning",
                        message=f"Could not re-parse source workbook for comparison: {exc}",
                        rule="source_workbook_readable",
                        suggested_analyst_action="Verify the uploaded template is intact.",
                    )
                )

        return passed, issues

    def _check_custom_run_report(
        self, report: CustomRunValidationReport
    ) -> tuple[int, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        passed = 0
        for check in report.checks:
            if check.status == "fail":
                severity = "critical"
                if check.check_type == "required_columns":
                    code = "CUSTOM_RUN_REQUIRED_COLUMNS"
                elif check.check_type == "ticker":
                    code = "TICKER_MISMATCH"
                else:
                    code = f"CUSTOM_RUN_{check.check_type.upper()}"
                issues.append(
                    ValidationIssue(
                        code=code,
                        severity=severity,
                        message=check.message,
                        cell_ref=check.cell_ref,
                        field_name=check.concept,
                        rule=check.check_type,
                        blocks_pipeline=True,
                        suggested_analyst_action="Fix the custom_run_filter and re-validate.",
                    )
                )
            elif check.status == "warn":
                issues.append(
                    ValidationIssue(
                        code=f"CUSTOM_RUN_{check.check_type.upper()}",
                        severity="warning",
                        message=check.message,
                        cell_ref=check.cell_ref,
                        field_name=check.concept,
                        rule=check.check_type,
                        suggested_analyst_action="Review the custom_run_filter warning.",
                    )
                )
            else:
                passed += 1
        return passed, issues

    def _check_provenance_rules(
        self,
        custom_run_mapping: CustomRunMapping,
        provenance_report: ProvenanceReport,
        completed_workbook_path: Path,
    ) -> tuple[int, list[ValidationIssue], list[str]]:
        issues: list[ValidationIssue] = []
        passed = 0
        unresolved: list[str] = []
        by_ref = {e.cell_ref: e for e in provenance_report.entries}

        for mapping in custom_run_mapping.entries:
            cell_ref = self.workbook_service.make_cell_ref(mapping.worksheet, mapping.cell)
            entry = by_ref.get(cell_ref)
            if entry is None:
                issues.append(
                    ValidationIssue(
                        code="MISSING_PROVENANCE",
                        severity="critical",
                        message=f"No provenance record for mapped cell {cell_ref}.",
                        worksheet=mapping.worksheet,
                        cell=mapping.cell,
                        cell_ref=cell_ref,
                        field_name=mapping.concept,
                        rule="every_written_cell_has_provenance",
                        blocks_pipeline=True,
                        suggested_analyst_action="Re-run workbook fill; every mapped cell needs provenance.",
                    )
                )
                unresolved.append(f"{mapping.concept}:{mapping.period}")
                continue

            if entry.status in {"unfilled", "unresolved"}:
                unresolved.append(entry.field_name or entry.concept)
                issues.append(
                    ValidationIssue(
                        code="REQUIRED_FIELD_UNRESOLVED",
                        severity="critical",
                        message=(
                            entry.failure_reason
                            or f"Required field '{entry.concept}' remains unresolved."
                        ),
                        worksheet=entry.worksheet,
                        cell=entry.cell,
                        cell_ref=entry.cell_ref,
                        field_name=entry.field_name or entry.concept,
                        rule="required_fields_resolved",
                        blocks_pipeline=True,
                        suggested_analyst_action="Provide an analyst-approved mapping or source value.",
                        source_references=[r for r in [entry.source_url, entry.xbrl_tag] if r],
                    )
                )
                continue

            if entry.status == "skipped_formula":
                passed += 1
                continue

            if entry.status == "preserved_existing" or entry.conflict_with_custom_run:
                issues.append(
                    ValidationIssue(
                        code="VALUE_CONFLICT",
                        severity="warning",
                        message=(
                            f"Workbook/custom_run value conflicts with filing for {entry.concept}."
                        ),
                        worksheet=entry.worksheet,
                        cell=entry.cell,
                        cell_ref=entry.cell_ref,
                        field_name=entry.field_name or entry.concept,
                        expected_value=entry.proposed_value or entry.original_source_value,
                        actual_value=entry.original_workbook_value
                        if entry.status == "preserved_existing"
                        else entry.custom_run_value,
                        rule="filing_controls_over_custom_run_unless_approved",
                        suggested_analyst_action=(
                            "Review both values; approve a transformation or keep the filing value."
                        ),
                        source_references=[r for r in [entry.source_url, entry.xbrl_tag] if r],
                    )
                )
                continue

            if entry.status == "filled":
                actual = self.workbook_service.get_cell_value(
                    completed_workbook_path, entry.worksheet, entry.cell
                )
                if not self._values_match(entry.value, actual):
                    issues.append(
                        ValidationIssue(
                            code="PROVENANCE_WORKBOOK_MISMATCH",
                            severity="critical",
                            message="Completed workbook value does not match provenance.",
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            expected_value=entry.value,
                            actual_value=actual,
                            rule="provenance_matches_workbook",
                            blocks_pipeline=True,
                            suggested_analyst_action="Re-run fill stage; investigate write path.",
                        )
                    )
                else:
                    passed += 1

        return passed, issues, unresolved

    def _check_source_reconciliation(
        self, provenance_report: ProvenanceReport
    ) -> tuple[int, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        passed = 0

        for entry in provenance_report.entries:
            if entry.status != "filled":
                continue

            # Unit conversion informational
            for transform in entry.transformations:
                if transform.type in {"unit_conversion", "scale_conversion"}:
                    issues.append(
                        ValidationIssue(
                            code="UNIT_CONVERSION_APPLIED",
                            severity="informational",
                            message=transform.description,
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            expected_value=transform.input_value,
                            actual_value=transform.output_value,
                            rule="record_unit_conversions",
                            source_references=[r for r in [entry.source_url] if r],
                        )
                    )
                elif transform.type == "sign_change":
                    issues.append(
                        ValidationIssue(
                            code="SIGN_CHANGE_APPLIED",
                            severity="informational",
                            message=transform.description,
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            rule="record_sign_changes",
                        )
                    )

            # Company-specific XBRL extension
            if entry.xbrl_tag and ":" in entry.xbrl_tag:
                taxonomy = entry.xbrl_tag.split(":", 1)[0]
                if taxonomy not in {"us-gaap", "dei", "ifrs-full"}:
                    issues.append(
                        ValidationIssue(
                            code="COMPANY_XBRL_EXTENSION",
                            severity="informational",
                            message=f"Company-specific XBRL extension tag used: {entry.xbrl_tag}",
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            rule="extension_tag_noted",
                        )
                    )
                else:
                    passed += 1
            else:
                passed += 1

            # custom_run vs filing conflict already handled; flag custom_run-only source
            if entry.source_type == "custom_run_filter" and entry.custom_run_value is not None:
                issues.append(
                    ValidationIssue(
                        code="CUSTOM_RUN_USED_WITHOUT_FILING",
                        severity="warning",
                        message=(
                            f"Value for {entry.concept} sourced from custom_run_filter "
                            "without a matching filing fact."
                        ),
                        worksheet=entry.worksheet,
                        cell=entry.cell,
                        cell_ref=entry.cell_ref,
                        field_name=entry.field_name or entry.concept,
                        actual_value=entry.value,
                        rule="prefer_filing_over_custom_run",
                        suggested_analyst_action="Confirm custom_run value against the filing.",
                    )
                )

        return passed, issues

    def _check_financial_statements(
        self, financial_statements: dict[str, Any]
    ) -> tuple[int, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        passed = 0

        balance = financial_statements.get("balance_sheet") or {}
        income = financial_statements.get("income_statement") or {}
        cash_flow = financial_statements.get("cash_flow") or {}

        # Balance sheet: Assets ≈ Liabilities + Equity
        assets_by_period = self._line_values(balance, {"Assets", "total assets"})
        liabilities_by_period = self._line_values(balance, {"Liabilities", "total liabilities"})
        equity_by_period = self._line_values(
            balance,
            {
                "StockholdersEquity",
                "stockholders equity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            },
        )

        periods = set(assets_by_period) & (set(liabilities_by_period) | set(equity_by_period))
        if not periods and assets_by_period:
            # Try liabilities+equity combined concept
            issues.append(
                ValidationIssue(
                    code="BALANCE_SHEET_INCOMPLETE",
                    severity="warning",
                    message="Could not fully reconcile Assets vs Liabilities+Equity (missing lines).",
                    rule="assets_equal_liabilities_plus_equity",
                    suggested_analyst_action="Verify balance-sheet extraction coverage.",
                )
            )
        for period in sorted(periods):
            assets = assets_by_period.get(period)
            liabilities = liabilities_by_period.get(period, 0.0)
            equity = equity_by_period.get(period, 0.0)
            if assets is None:
                continue
            rhs = (liabilities or 0.0) + (equity or 0.0)
            tolerance = abs(assets) * self.thresholds.balance_sheet_tolerance_pct
            if abs(assets - rhs) > max(tolerance, 1.0):
                issues.append(
                    ValidationIssue(
                        code="BALANCE_SHEET_IMBALANCE",
                        severity="critical",
                        message=(
                            f"Balance sheet does not balance for {period}: "
                            f"Assets={assets}, L+E={rhs}."
                        ),
                        field_name="Assets",
                        expected_value=assets,
                        actual_value=rhs,
                        rule="assets_equal_liabilities_plus_equity",
                        blocks_pipeline=True,
                        suggested_analyst_action="Investigate missing or mis-signed balance-sheet lines.",
                    )
                )
            else:
                passed += 1

        # Cash flow ending cash vs BS cash
        cf_cash = self._line_values(
            cash_flow,
            {
                "CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                "ending cash",
            },
        )
        bs_cash = self._line_values(
            balance,
            {"CashAndCashEquivalentsAtCarryingValue", "cash and cash equivalents"},
        )
        for period in sorted(set(cf_cash) & set(bs_cash)):
            a, b = cf_cash[period], bs_cash[period]
            if a is None or b is None:
                continue
            tol = abs(b) * self.thresholds.cash_reconcile_tolerance_pct
            if abs(a - b) > max(tol, 1.0):
                issues.append(
                    ValidationIssue(
                        code="CASH_RECONCILE_MISMATCH",
                        severity="warning",
                        message=f"Ending cash does not reconcile to BS cash for {period}.",
                        field_name="Cash",
                        expected_value=b,
                        actual_value=a,
                        rule="cf_ending_cash_reconciles_bs",
                        suggested_analyst_action="Compare cash-flow ending cash to balance-sheet cash.",
                    )
                )
            else:
                passed += 1

        # Net income IS vs CF
        is_ni = self._line_values(income, {"NetIncomeLoss", "net income", "ProfitLoss"})
        cf_ni = self._line_values(
            cash_flow,
            {"NetIncomeLoss", "ProfitLoss", "net income"},
        )
        for period in sorted(set(is_ni) & set(cf_ni)):
            a, b = is_ni[period], cf_ni[period]
            if a is None or b is None:
                continue
            tol = abs(a) * self.thresholds.net_income_tolerance_pct
            if abs(a - b) > max(tol, 1.0):
                issues.append(
                    ValidationIssue(
                        code="NET_INCOME_RECONCILE_MISMATCH",
                        severity="warning",
                        message=f"Net income differs between IS and CF for {period}.",
                        field_name="Net Income",
                        expected_value=a,
                        actual_value=b,
                        rule="ni_reconciles_is_cf",
                        suggested_analyst_action="Review NI mapping on income statement vs cash flow.",
                    )
                )
            else:
                passed += 1

        # Period mixing: annual vs quarterly labels in same series
        annual = set(financial_statements.get("annual_periods") or [])
        quarterly = set(financial_statements.get("quarterly_periods") or [])
        overlap = annual & quarterly
        if overlap:
            issues.append(
                ValidationIssue(
                    code="PERIOD_MIXING",
                    severity="critical",
                    message=f"Annual and quarterly periods overlap incorrectly: {sorted(overlap)}",
                    rule="no_annual_quarterly_mixing",
                    blocks_pipeline=True,
                    suggested_analyst_action="Separate annual and quarterly series before analysis.",
                )
            )
        else:
            passed += 1

        return passed, issues

    def _check_plausibility(
        self, provenance_report: ProvenanceReport
    ) -> tuple[int, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []
        passed = 0

        for entry in provenance_report.entries:
            if entry.status != "filled" or entry.value is None:
                continue
            try:
                numeric = float(entry.value)
            except (TypeError, ValueError):
                passed += 1
                continue

            concept = (entry.field_name or entry.concept or "").lower()

            if self._is_impossible_value(concept, numeric):
                issues.append(
                    ValidationIssue(
                        code="UNEXPECTED_NEGATIVE",
                        severity="warning",
                        message=f"Unexpected negative value for {entry.concept}: {numeric}",
                        worksheet=entry.worksheet,
                        cell=entry.cell,
                        cell_ref=entry.cell_ref,
                        field_name=entry.field_name or entry.concept,
                        actual_value=numeric,
                        rule="plausibility_negative_check",
                        suggested_analyst_action="Confirm sign convention and source mapping.",
                    )
                )
                continue

            if "tax" in concept and "rate" in concept:
                if (
                    numeric < self.thresholds.extreme_tax_rate_low
                    or numeric > self.thresholds.extreme_tax_rate_high
                ):
                    issues.append(
                        ValidationIssue(
                            code="EXTREME_TAX_RATE",
                            severity="warning",
                            message=f"Abnormal effective tax rate: {numeric}",
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            actual_value=numeric,
                            rule="extreme_tax_rate",
                            suggested_analyst_action="Review tax rate against the filing footnote.",
                        )
                    )
                    continue

            if "margin" in concept:
                if (
                    numeric < self.thresholds.extreme_margin_low
                    or numeric > self.thresholds.extreme_margin_high
                ):
                    issues.append(
                        ValidationIssue(
                            code="EXTREME_MARGIN",
                            severity="warning",
                            message=f"Extreme margin value: {numeric}",
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            actual_value=numeric,
                            rule="extreme_margin",
                            suggested_analyst_action="Review margin calculation and units.",
                        )
                    )
                    continue

            if "roic" in concept or "roce" in concept:
                if (
                    numeric < self.thresholds.extreme_roic_low
                    or numeric > self.thresholds.extreme_roic_high
                ):
                    issues.append(
                        ValidationIssue(
                            code="EXTREME_ROIC",
                            severity="warning",
                            message=f"Unusual ROIC/ROCE: {numeric}",
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            actual_value=numeric,
                            rule="extreme_roic",
                            suggested_analyst_action="Review invested-capital inputs.",
                        )
                    )
                    continue

            # Possible scale mismatch vs original source
            if entry.original_source_value is not None:
                try:
                    source_num = float(entry.original_source_value)
                    if source_num != 0 and abs(numeric) > 0:
                        ratio = abs(source_num / numeric)
                        if ratio >= self.thresholds.scale_mismatch_ratio and not any(
                            t.type in {"unit_conversion", "scale_conversion"}
                            for t in entry.transformations
                        ):
                            issues.append(
                                ValidationIssue(
                                    code="POSSIBLE_SCALE_MISMATCH",
                                    severity="warning",
                                    message=(
                                        f"Possible scale mismatch for {entry.concept}: "
                                        f"source={source_num}, workbook={numeric}."
                                    ),
                                    worksheet=entry.worksheet,
                                    cell=entry.cell,
                                    cell_ref=entry.cell_ref,
                                    field_name=entry.field_name or entry.concept,
                                    expected_value=source_num,
                                    actual_value=numeric,
                                    rule="scale_mismatch_detection",
                                    suggested_analyst_action=(
                                        "Confirm dollars vs thousands vs millions."
                                    ),
                                )
                            )
                            continue
                except (TypeError, ValueError):
                    pass

            # YTD treated as standalone quarter
            if entry.period_classification == "year_to_date" and "q" in entry.period.lower():
                if "ytd" not in entry.period.lower() and "year" not in (
                    entry.reasoning or ""
                ).lower():
                    issues.append(
                        ValidationIssue(
                            code="YTD_AS_STANDALONE_QUARTER",
                            severity="warning",
                            message=(
                                f"Period '{entry.period}' classified as YTD; "
                                "ensure it is not treated as a standalone quarter."
                            ),
                            worksheet=entry.worksheet,
                            cell=entry.cell,
                            cell_ref=entry.cell_ref,
                            field_name=entry.field_name or entry.concept,
                            rule="ytd_not_standalone_quarter",
                            suggested_analyst_action="Confirm period classification before analysis.",
                        )
                    )
                    continue

            passed += 1

        return passed, issues

    @staticmethod
    def _line_values(
        statement: dict[str, Any], concept_names: set[str]
    ) -> dict[str, float | None]:
        """Extract period→value map for matching line items."""
        lowered = {c.lower() for c in concept_names}
        result: dict[str, float | None] = {}
        for item in statement.get("line_items") or []:
            concept = str(item.get("concept") or "").lower()
            label = str(item.get("label") or "").lower()
            tag = str(item.get("xbrl_tag") or "").lower()
            if concept not in lowered and label not in lowered and tag not in lowered:
                # also allow substring match on concept aliases
                if not any(alias in concept or alias in label for alias in lowered):
                    continue
            for value in item.get("values") or []:
                period = value.get("period")
                if not period:
                    continue
                raw = value.get("value")
                try:
                    result[str(period)] = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    result[str(period)] = None
        return result

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
        if numeric < 0 and any(
            token in lowered for token in ("revenue", "assets", "cash flow", "total assets")
        ):
            return True
        return False
