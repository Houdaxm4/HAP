"""Stage: validate Custom_Run + prefill + statement SEC validation + analyst review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models.analysis import Analysis
from models.completion import CompletionReport
from models.custom_run import CustomRunData
from models.pipeline import DecisionLogEntry
from models.prefill_validation import PrefillValidationStatus
from models.provenance import ProvenanceReport
from models.statement_validation import StatementValidationDecision
from models.validation import DiscrepancyReport, ValidationCheck
from services.analyst_review_service import AnalystReviewService
from services.completion_scope import AnalysisTypeMode, normalize_analysis_type
from services.custom_run_validation import CustomRunValidationService
from services.output_service import OutputService
from services.prefill_validation_service import PrefillValidationService
from services.expected_return_validation_service import ExpectedReturnValidationService
from services.final_recommendation_service import FinalRecommendationService
from services.roic_validation_service import RoicValidationService
from services.statement_validation_service import StatementValidationService
from services.valuation_validation_service import ValuationValidationService


class ValidateWorkbookStage:
    """
    Phase B — after completion:

    1. Custom_Run structural validation
    2. Prefill vs SEC comparison for ALREADY_PRESENT cells
    3. Material statement validation (workbook vs SEC) — no rewrites
    4. Analyst review of economically meaningful movements
    5. ROIC / NOPAT / Invested Capital review — no workbook writes
    6. Expected Return / EPS growth review — no workbook writes
    7. Valuation / MOS / entry-price review — no formula writes
    8. Final investment recommendation synthesis
    """

    def __init__(
        self,
        custom_run_validation: CustomRunValidationService | None = None,
        prefill_validation: PrefillValidationService | None = None,
        statement_validation: StatementValidationService | None = None,
        analyst_review: AnalystReviewService | None = None,
        roic_validation: RoicValidationService | None = None,
        expected_return_validation: ExpectedReturnValidationService | None = None,
        valuation_validation: ValuationValidationService | None = None,
        final_recommendation: FinalRecommendationService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.custom_run_validation = custom_run_validation or CustomRunValidationService()
        self.prefill_validation = prefill_validation or PrefillValidationService()
        self.statement_validation = statement_validation or StatementValidationService()
        self.analyst_review = analyst_review or AnalystReviewService()
        self.roic_validation = roic_validation or RoicValidationService()
        self.expected_return_validation = (
            expected_return_validation or ExpectedReturnValidationService()
        )
        self.valuation_validation = valuation_validation or ValuationValidationService()
        self.final_recommendation = final_recommendation or FinalRecommendationService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run: CustomRunData,
        provenance_report: ProvenanceReport,
        completed_workbook_path: Path,
        completion_report: CompletionReport | None = None,
        company_facts: dict[str, Any] | None = None,
        *,
        skip_annual_deep_review: bool = False,
    ) -> tuple[DiscrepancyReport, str, str, DecisionLogEntry]:
        report = self.custom_run_validation.validate(analysis.analysis_id, custom_run)

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

        discrepancy_only = DiscrepancyReport(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            checks=[],
            summary="",
        )

        if completion_report is not None:
            prefill = self.prefill_validation.validate(completion_report)
            self.output_service.write_json(
                analysis.analysis_id,
                "prefill_validation_report.json",
                prefill,
            )
            for entry in prefill.entries:
                if entry.status == PrefillValidationStatus.VALIDATED:
                    report.checks.append(
                        ValidationCheck(
                            cell_ref=entry.cell_ref,
                            worksheet=entry.sheet,
                            cell=entry.cell,
                            concept=entry.metric,
                            period=entry.period,
                            check_type="value_match",
                            status="pass",
                            expected_value=entry.sec_value,
                            actual_value=entry.workbook_value,
                            message=entry.reason,
                            source_document=entry.source_evidence,
                        )
                    )
                elif entry.status == PrefillValidationStatus.DISCREPANCY:
                    check = ValidationCheck(
                        cell_ref=entry.cell_ref,
                        worksheet=entry.sheet,
                        cell=entry.cell,
                        concept=entry.metric,
                        period=entry.period,
                        check_type="inconsistency",
                        status="fail",
                        expected_value=entry.sec_value,
                        actual_value=entry.workbook_value,
                        message=(
                            f"{entry.reason} "
                            f"(diff={entry.difference}, pct={entry.difference_pct})"
                        ),
                        source_document=entry.source_evidence,
                    )
                    report.checks.append(check)
                    discrepancy_only.checks.append(check)
                else:
                    report.checks.append(
                        ValidationCheck(
                            cell_ref=entry.cell_ref,
                            worksheet=entry.sheet,
                            cell=entry.cell,
                            concept=entry.metric,
                            period=entry.period,
                            check_type="missing_value",
                            status="warn",
                            expected_value=entry.sec_value,
                            actual_value=entry.workbook_value,
                            message=entry.reason,
                            source_document=entry.source_evidence,
                        )
                    )

            discrepancy_only.fail_count = len(discrepancy_only.checks)
            discrepancy_only.pass_count = 0
            discrepancy_only.warn_count = 0
            discrepancy_only.summary = (
                f"{discrepancy_only.fail_count} statement discrepancies "
                f"(not silently overwritten). {prefill.summary}"
            )
        else:
            discrepancy_only = report.model_copy(deep=True)

        # --- Statement validation + analyst review (read-only on workbook) ---
        stmt_note = ""
        review_note = ""
        stmt_report = None
        review = None
        mode = normalize_analysis_type(analysis.analysis_type)
        run_statement_validation = (
            company_facts is not None
            and completed_workbook_path.exists()
            and not (skip_annual_deep_review and mode == AnalysisTypeMode.QUARTERLY_UPDATE)
        )
        # Quarterly lean path: skip 10y statement validation; use quarter review instead.
        if (
            skip_annual_deep_review
            and mode == AnalysisTypeMode.QUARTERLY_UPDATE
            and company_facts is not None
            and completed_workbook_path.exists()
        ):
            # Only quarterly lines — still useful, avoid annual bulk
            stmt_report = self.statement_validation.validate(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
                company_facts=company_facts,
                include_quarterly=True,
                annual_lines=False,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "statement_validation_report.json",
                stmt_report,
            )
            stmt_note = f" {stmt_report.summary}"
            run_statement_validation = False

        if run_statement_validation:
            stmt_report = self.statement_validation.validate(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
                company_facts=company_facts,
                include_quarterly=(mode == AnalysisTypeMode.QUARTERLY_UPDATE),
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "statement_validation_report.json",
                stmt_report,
            )
            for entry in stmt_report.entries:
                if entry.decision == StatementValidationDecision.VALIDATED:
                    report.checks.append(
                        ValidationCheck(
                            cell_ref=entry.workbook_cell,
                            worksheet=entry.workbook_cell.split("!")[0],
                            cell=entry.workbook_cell.split("!")[-1],
                            concept=entry.metric,
                            period=entry.fiscal_period,
                            check_type="value_match",
                            status="pass",
                            expected_value=entry.sec_value,
                            actual_value=entry.workbook_value,
                            message=entry.reason,
                            source_document=entry.accession_number,
                            xbrl_tag=entry.sec_concept,
                        )
                    )
                elif entry.decision == StatementValidationDecision.DISCREPANCY:
                    check = ValidationCheck(
                        cell_ref=entry.workbook_cell,
                        worksheet=entry.workbook_cell.split("!")[0],
                        cell=entry.workbook_cell.split("!")[-1],
                        concept=entry.metric,
                        period=entry.fiscal_period,
                        check_type="inconsistency",
                        status="fail",
                        expected_value=entry.sec_value,
                        actual_value=entry.workbook_value,
                        message=entry.reason,
                        source_document=entry.accession_number,
                        xbrl_tag=entry.sec_concept,
                    )
                    report.checks.append(check)
                    discrepancy_only.checks.append(check)
                elif entry.decision == StatementValidationDecision.REVIEW_REQUIRED:
                    report.checks.append(
                        ValidationCheck(
                            cell_ref=entry.workbook_cell,
                            worksheet=entry.workbook_cell.split("!")[0],
                            cell=entry.workbook_cell.split("!")[-1],
                            concept=entry.metric,
                            period=entry.fiscal_period,
                            check_type="inconsistency",
                            status="warn",
                            expected_value=entry.sec_value,
                            actual_value=entry.workbook_value,
                            message=entry.reason,
                            source_document=entry.accession_number,
                            xbrl_tag=entry.sec_concept,
                        )
                    )

            review = self.analyst_review.review(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                validation=stmt_report,
                company_facts=company_facts,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "analyst_review_report.json",
                review,
            )
            stmt_note = f" {stmt_report.summary}"
            review_note = f" {review.summary}"
            discrepancy_only.fail_count = sum(
                1 for c in discrepancy_only.checks if c.status == "fail"
            )
            discrepancy_only.summary = (
                f"{discrepancy_only.fail_count} discrepancies recorded "
                f"(not silently overwritten).{stmt_note}"
            )

        # --- ROIC / NOPAT / Invested Capital review (read-only) ---
        roic_note = ""
        roic_report = None
        if completed_workbook_path.exists() and not skip_annual_deep_review:
            roic_report = self.roic_validation.validate(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "roic_validation_report.json",
                roic_report,
            )
            roic_review = self.roic_validation.build_analyst_review(roic_report)
            self.output_service.write_json(
                analysis.analysis_id,
                "roic_analyst_review.json",
                roic_review,
            )
            roic_note = f" {roic_report.summary}"

        # --- Expected Return / EPS growth review (read-only) ---
        er_note = ""
        er_report = None
        if completed_workbook_path.exists() and not skip_annual_deep_review:
            er_report = self.expected_return_validation.validate(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
                company_facts=company_facts,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "expected_return_validation_report.json",
                er_report,
            )
            er_review = self.expected_return_validation.build_analyst_review(er_report)
            self.output_service.write_json(
                analysis.analysis_id,
                "expected_return_analyst_review.json",
                er_review,
            )
            er_note = f" {er_report.summary}"

        # --- Valuation / MOS / entry price (read-only on formulas) ---
        val_note = ""
        val_report = None
        if completed_workbook_path.exists() and not skip_annual_deep_review:
            val_report = self.valuation_validation.validate(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "valuation_validation_report.json",
                val_report,
            )
            val_review = self.valuation_validation.build_analyst_review(val_report)
            self.output_service.write_json(
                analysis.analysis_id,
                "valuation_analyst_review.json",
                val_review,
            )
            val_note = f" {val_report.summary}"

        # --- Final investment recommendation synthesis ---
        rec_note = ""
        if not skip_annual_deep_review and (val_report is not None or roic_report is not None):
            final_rec = self.final_recommendation.synthesize(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                valuation=val_report.model_dump() if val_report else None,
                roic=roic_report.model_dump() if roic_report else None,
                expected_return=er_report.model_dump() if er_report else None,
                statement_validation=stmt_report.model_dump() if stmt_report else None,
                analyst_review=review.model_dump() if review else None,
            )
            self.output_service.write_json(
                analysis.analysis_id,
                "final_recommendation_report.json",
                final_rec,
            )
            rec_note = f" {final_rec.summary}"
        elif skip_annual_deep_review:
            rec_note = " [quarterly lean path: skipped ROIC/ER/valuation/recommendation]"

        report.pass_count = sum(1 for c in report.checks if c.status == "pass")
        report.warn_count = sum(1 for c in report.checks if c.status == "warn")
        report.fail_count = sum(1 for c in report.checks if c.status == "fail")
        if report.fail_count:
            report.summary = (
                f"{report.fail_count} failed, {report.warn_count} warnings, "
                f"{report.pass_count} passed."
                f"{stmt_note}{review_note}{roic_note}{er_note}{val_note}{rec_note}"
            )
        elif report.warn_count:
            report.summary = (
                f"Validation completed with {report.warn_count} warnings and "
                f"{report.pass_count} passed checks."
                f"{stmt_note}{review_note}{roic_note}{er_note}{val_note}{rec_note}"
            )
        else:
            report.summary = (
                f"All {report.pass_count} checks passed."
                f"{stmt_note}{review_note}{roic_note}{er_note}{val_note}{rec_note}"
            )

        discrepancy_path = self.output_service.write_json(
            analysis.analysis_id,
            "discrepancy_report.json",
            discrepancy_only,
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
