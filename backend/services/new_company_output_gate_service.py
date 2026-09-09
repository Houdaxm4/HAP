"""New Company output-readiness gates A–K."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models.new_company import (
    LeaseRateReview,
    NewCompanyBuybackReport,
    NewCompanyCurrentDataReport,
    NewCompanyLeaseReport,
    NewCompanyOutputGateReport,
    NewCompanyPe10Report,
    NewCompanyProjectionReport,
    NewCompanyRdReport,
    NewCompanyStatementValidationReport,
    NewCompanyTaxReport,
    ProjectionConfidence,
    RdUsefulLifeDecision,
    TenYearPeriodReport,
    TenYearSourceCoverageReport,
)
from models.annual_update import AnnualValuationOutputs
from services.excel_recalc_service import ExcelRecalcReport, genuine_excel_com_recalc


class NewCompanyOutputGateService:
    def evaluate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        periods: TenYearPeriodReport | None,
        coverage: TenYearSourceCoverageReport | None,
        statements: NewCompanyStatementValidationReport | None,
        pe10: NewCompanyPe10Report | None,
        tax: NewCompanyTaxReport | None,
        rd_decision: RdUsefulLifeDecision | None,
        rd: NewCompanyRdReport | None,
        leases: NewCompanyLeaseReport | None,
        lease_review: LeaseRateReview | None,
        buybacks: NewCompanyBuybackReport | None,
        current: NewCompanyCurrentDataReport | None,
        projection: NewCompanyProjectionReport | None,
        recalc: ExcelRecalcReport | None,
        valuation: AnnualValuationOutputs | None,
        word_authorized_attempt: bool = False,
    ) -> NewCompanyOutputGateReport:
        blockers: list[str] = []
        warnings: list[str] = []
        gates: dict[str, str] = {}

        # Gate A — template and period integrity
        if (
            periods is None
            or periods.template_family != "industrial_template"
            or len(periods.fiscal_years) != 10
            or not periods.chronology_ok
        ):
            blockers.append("NEW_COMPANY_ANNUAL_PERIOD_RANGE_INVALID")
            gates["A_template_period"] = "fail"
        elif periods.latest_quarter is None:
            blockers.append("NEW_COMPANY_QUARTER_NOT_IDENTIFIED")
            gates["A_template_period"] = "fail"
        else:
            gates["A_template_period"] = "pass"
        if coverage is not None and not coverage.complete:
            blockers.append("TEN_YEAR_SEC_COVERAGE_INCOMPLETE")
            gates["A_sec_coverage"] = "fail"
        else:
            gates["A_sec_coverage"] = "pass" if coverage and coverage.complete else "fail"
            if coverage is None:
                blockers.append("TEN_YEAR_SEC_COVERAGE_INCOMPLETE")
        if coverage is not None and not coverage.lookback_complete:
            warnings.append("RD_LOOKBACK_COVERAGE_INCOMPLETE")

        # Gate B — financial-statement completeness
        if statements is None or statements.unresolved_material:
            blockers.append("NEW_COMPANY_ANNUAL_PERIOD_RANGE_INVALID" if statements is None else "statement_material_unresolved")
            gates["B_statements"] = "fail"
        else:
            gates["B_statements"] = "pass"
            warnings.extend(statements.unresolved_material)

        # Gate C — PE10/E10
        if pe10 is None or any(o.missing for o in pe10.fiscal_year_pe10):
            blockers.append("TEN_YEAR_PE10_COVERAGE_INCOMPLETE")
            gates["C_pe10"] = "fail"
        elif any(o.missing for o in pe10.fiscal_year_e10):
            blockers.append("TEN_YEAR_E10_COVERAGE_INCOMPLETE")
            gates["C_pe10"] = "fail"
        else:
            gates["C_pe10"] = "pass"
        if pe10:
            if pe10.current_pe10 is None or pe10.current_pe10.value is None:
                blockers.append("TEN_YEAR_PE10_COVERAGE_INCOMPLETE")
                gates["C_pe10"] = "fail"
            if pe10.current_e10 is None or pe10.current_e10.value is None:
                warnings.append("TEN_YEAR_E10_COVERAGE_INCOMPLETE: current E10 missing")
            for w in pe10.warnings:
                if "PE10_FISCAL_DATE_MISMATCH" in w:
                    warnings.append(w)
                elif "PE10_PERIOD_NOTE" in w:
                    warnings.append(w)

        # Gate D — tax
        if tax is None or not tax.complete:
            blockers.append("TEN_YEAR_TAX_COVERAGE_INCOMPLETE")
            gates["D_tax"] = "fail"
        else:
            gates["D_tax"] = "pass"
            if any(y.reconciliation_status not in {"ok", ""} for y in tax.years):
                warnings.append("TAX_RECONCILIATION_FAILED")
                if any(
                    y.reconciliation_status == "TAX_EFFECTIVE_RATE_RECONCILIATION_FAILED"
                    for y in tax.years
                ):
                    blockers.append("TAX_RECONCILIATION_FAILED")
                    gates["D_tax"] = "fail"

        # Gate E — R&D
        if rd_decision is None or rd_decision.selected_useful_life is None:
            blockers.append("RD_USEFUL_LIFE_EVIDENCE_WEAK")
            gates["E_rd"] = "fail"
        else:
            warnings.append("RD_USEFUL_LIFE_AGENT_SELECTED")
            if rd_decision.blocking or rd_decision.blocking_reasons:
                for r in rd_decision.blocking_reasons:
                    warnings.append(r)
                if rd_decision.blocking:
                    blockers.append("RD_USEFUL_LIFE_EVIDENCE_WEAK")
                    gates["E_rd"] = "fail"
                else:
                    gates["E_rd"] = "pass"
            else:
                gates["E_rd"] = "pass"
        if rd is None or not rd.lookback_complete:
            blockers.append("RD_LOOKBACK_COVERAGE_INCOMPLETE")
            gates["E_rd"] = "fail"
        elif not rd.capitalization_ok:
            blockers.append("RD_CAPITALIZATION_FAILED")
            gates["E_rd"] = "fail"

        # Gate F — leases (blocking until analyst approval)
        if leases is None or not leases.complete:
            blockers.append("LEASE_HISTORY_INCOMPLETE")
            gates["F_leases"] = "fail"
        else:
            gates["F_leases"] = "pass"
        review = lease_review or (leases.review if leases else None)
        if review is None or review.proposed_rate is None:
            blockers.append("LEASE_RATE_REVIEW_REQUIRED")
            gates["F_lease_rate"] = "fail"
        elif review.blocking or review.status in {
            "LEASE_RATE_REVIEW_PENDING",
            "pending",
        }:
            blockers.append("LEASE_RATE_REVIEW_PENDING")
            warnings.append("LEASE_RATE_ESTIMATED")
            gates["F_lease_rate"] = "fail"
        else:
            gates["F_lease_rate"] = "pass"
            if review.analyst_action == "correct":
                warnings.append("LEASE_RATE_ANALYST_OVERRIDDEN")

        # Gate G — buybacks
        if buybacks is None:
            blockers.append("BUYBACK_DOLLARS_COVERAGE_INCOMPLETE")
            gates["G_buybacks"] = "fail"
        else:
            dollar_gap = any(
                y.dollars is None and (y.absence_class is None or y.absence_class.value == "unresolved")
                for y in buybacks.years
            )
            share_gap = any(
                y.shares is None
                and not y.shares_derived
                and (y.absence_class is None or y.absence_class.value == "unresolved")
                for y in buybacks.years
            )
            if dollar_gap:
                blockers.append("BUYBACK_DOLLARS_COVERAGE_INCOMPLETE")
                gates["G_buybacks"] = "fail"
            elif share_gap:
                blockers.append("BUYBACK_SHARES_COVERAGE_INCOMPLETE")
                gates["G_buybacks"] = "fail"
            else:
                gates["G_buybacks"] = "pass"
            for w in buybacks.warnings:
                if "DERIVED" in w:
                    warnings.append(w)
                elif "RECONCILIATION" in w:
                    warnings.append("BUYBACK_RECONCILIATION_FAILED")

        # Gate H — current data
        if current is not None and current.as_of_mismatch:
            warnings.append("CURRENT_DATA_AS_OF_DATE_MISMATCH")
            gates["H_current"] = "warn"
        else:
            gates["H_current"] = "pass" if current else "fail"
            if current is None:
                blockers.append("CURRENT_DATA_AS_OF_DATE_MISMATCH")

        # Gate I — projection integrity (Q2/Q3)
        q = periods.latest_quarter if periods else None
        if q in {2, 3}:
            if projection is None or projection.seasonality_adjusted_roic is None:
                blockers.append("PROJECTED_ROIC_FAILED")
                gates["I_projection"] = "fail"
            elif projection.seasonality_adjusted_roce is None:
                blockers.append("PROJECTED_ROCE_FAILED")
                gates["I_projection"] = "fail"
            elif projection.confidence == ProjectionConfidence.UNRELIABLE:
                blockers.append("SEASONALITY_PROJECTION_UNRELIABLE")
                gates["I_projection"] = "fail"
            else:
                gates["I_projection"] = "pass"
                if projection.confidence == ProjectionConfidence.LOW:
                    warnings.append("SEASONALITY_HISTORY_INSUFFICIENT")
        else:
            gates["I_projection"] = "n/a"

        # Gate J — recalculation (genuine Excel COM only; do not bypass)
        if not genuine_excel_com_recalc(recalc):
            blockers.append("WORKBOOK_RECALCULATION_INCOMPLETE")
            gates["J_recalc"] = "fail"
        else:
            gates["J_recalc"] = "pass"

        # Gate K — valuation and report authorization
        if valuation is None:
            blockers.append("NEW_COMPANY_REPORT_NOT_AUTHORIZED")
            gates["K_valuation"] = "fail"
        else:
            required = [
                valuation.expected_annual_return,
                valuation.expected_return_with_dividends,
                valuation.current_graham_intrinsic_value,
                valuation.nopat,
                valuation.invested_capital,
                valuation.roic,
            ]
            if any(v is None for v in required):
                blockers.append("NEW_COMPANY_REPORT_NOT_AUTHORIZED")
                gates["K_valuation"] = "fail"
            else:
                gates["K_valuation"] = "pass"

        seen: set[str] = set()
        uniq: list[str] = []
        for b in blockers:
            if b not in seen:
                seen.add(b)
                uniq.append(b)
        blockers = uniq
        authorized = not blockers
        if not authorized:
            if "NEW_COMPANY_REPORT_NOT_AUTHORIZED" not in blockers:
                blockers.append("NEW_COMPANY_REPORT_NOT_AUTHORIZED")
            gates["report_authorization"] = "blocked"
            status = "NEEDS_REVIEW"
            if "LEASE_RATE_REVIEW_PENDING" in blockers:
                status = "AWAITING_ANALYST_REVIEW"
        else:
            gates["report_authorization"] = "authorized"
            status = "ok"
        if word_authorized_attempt and not authorized:
            warnings.append("NEW_COMPANY_REPORT_NOT_AUTHORIZED")

        return NewCompanyOutputGateReport(
            analysis_id=analysis_id,
            ticker=ticker,
            status=status,
            gates=gates,
            blockers=blockers,
            warnings=warnings,
            report_authorized=authorized,
            summary=(
                f"New Company gates={status}; blockers={len(blockers)}; "
                f"warnings={len(warnings)}; authorized={authorized}."
            ),
        )
