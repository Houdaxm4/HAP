"""New Company initiation runner — ten-year coverage, autonomous lease/R&D decisions, Word."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from models.new_company import (
    CLOUD_PENDING_WINDOWS_CERTIFICATION,
    LeaseRateReview,
    NewCompanyCurrentDataReport,
    NewCompanyRunState,
    NewCompanyWorkflowState,
    CurrentDataAsOf,
)
from services.completion_scope import quarterly_analysis_required
from services.annual_formula_guard_service import AnnualFormulaGuardService
from services.annual_valuation_extract_service import AnnualValuationExtractService
from services.current_data_refresh_service import CurrentDataRefreshService
from services.excel_recalc_service import ExcelRecalcService, genuine_excel_com_recalc
from services.cost_recast_writer import CostRecastWriter
from services.new_company_buyback_service import NewCompanyBuybackService
from services.new_company_deliverables_service import NewCompanyDeliverablesService
from services.new_company_lease_service import NewCompanyLeaseService
from services.new_company_output_gate_service import NewCompanyOutputGateService
from services.new_company_pe10_service import NewCompanyPe10Service
from services.new_company_period_service import NewCompanyPeriodService
from services.quarterly_presentation_service import (
    QuarterlyPresentationService,
    quarter_incorporated,
)
from services.new_company_projection_service import (
    NewCompanyProjectionService,
    resolve_workbook_wacc,
)
from services.new_company_rd_service import NewCompanyRdService
from services.new_company_seasonality_service import NewCompanySeasonalityService
from services.new_company_sec_coverage_service import NewCompanySecCoverageService
from services.new_company_statement_validation_service import NewCompanyStatementValidationService
from services.new_company_tax_service import NewCompanyTaxService
from services.new_company_valuation_service import NewCompanyValuationService
from services.output_service import OutputService


def _fy_int(token: str | None) -> int:
    digits = "".join(ch for ch in str(token or "") if ch.isdigit())
    return int(digits) if digits else 0


def _certification_status(workflow, lease_review, recalc, gate) -> str:
    """COMPLETE only after genuine Excel COM. Cloud COM-unavailable + selected rate → pending Windows."""
    if workflow == NewCompanyWorkflowState.COMPLETE and genuine_excel_com_recalc(recalc):
        return NewCompanyWorkflowState.COMPLETE.value
    if workflow == NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW:
        return NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW.value
    lease_ok = bool(
        lease_review
        and not lease_review.blocking
        and (lease_review.selected_rate is not None or lease_review.proposed_rate is not None)
    )
    recalc_unavailable = bool(recalc is not None and recalc.status == "UNAVAILABLE" and not recalc.com_invoked)
    blockers = list(gate.blockers) if gate is not None else []
    com_blocked = "WORKBOOK_RECALCULATION_INCOMPLETE" in blockers
    other = [
        b
        for b in blockers
        if b not in {"WORKBOOK_RECALCULATION_INCOMPLETE", "NEW_COMPANY_REPORT_NOT_AUTHORIZED"}
    ]
    if lease_ok and recalc_unavailable and com_blocked and not other:
        return CLOUD_PENDING_WINDOWS_CERTIFICATION
    return workflow.value if hasattr(workflow, "value") else str(workflow)


class NewCompanyRunner:
    def __init__(self, output_service: OutputService | None = None) -> None:
        self.output_service = output_service or OutputService()
        self.periods = NewCompanyPeriodService()
        self.coverage = NewCompanySecCoverageService()
        self.statements = NewCompanyStatementValidationService()
        self.pe10 = NewCompanyPe10Service()
        self.tax = NewCompanyTaxService()
        self.rd = NewCompanyRdService()
        self.leases = NewCompanyLeaseService()
        self.buybacks = NewCompanyBuybackService()
        self.cost_recast = CostRecastWriter()
        self.seasonality = NewCompanySeasonalityService()
        self.projection = NewCompanyProjectionService()
        self.gates = NewCompanyOutputGateService()
        self.deliverables = NewCompanyDeliverablesService()
        self.valuation_extract = AnnualValuationExtractService()
        self.valuation_judgment = NewCompanyValuationService()
        self.excel_recalc = ExcelRecalcService()
        self.guard = AnnualFormulaGuardService()
        self.current = CurrentDataRefreshService()
        self.quarterly_presentation = QuarterlyPresentationService()

    def run(
        self,
        *,
        analysis_id: str,
        ticker: str,
        company: str,
        template_path: Path,
        working_path: Path,
        custom_run_path: Path | None,
        company_facts: dict[str, Any] | None = None,
        sec_manifest: dict[str, Any] | None = None,
        lease_review_override: dict[str, Any] | None = None,
        rd_override: dict[str, Any] | None = None,
        tax_year_inputs: dict[str, dict[str, Any]] | None = None,
        finalize: bool = False,
        live_price: float | None = None,
        wacc: float | None = None,
        after_tax_cost_of_debt: float | None = None,
        treasury_yield: float | None = None,
        prepare_working: bool = True,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        timings: list[dict[str, Any]] = []

        def timed(name: str, fn):
            start = time.perf_counter()
            result = fn()
            timings.append({"stage": name, "elapsed_ms": (time.perf_counter() - start) * 1000.0})
            return result

        if prepare_working:
            working_path.parent.mkdir(parents=True, exist_ok=True)
            if Path(working_path).resolve() != Path(template_path).resolve():
                shutil.copy2(template_path, working_path)

        periods = timed(
            "classify_and_detect_periods",
            lambda: self.periods.detect(
                analysis_id=analysis_id, ticker=ticker, workbook_path=working_path
            ),
        )
        years = periods.fiscal_years
        coverage = timed(
            "ten_year_sec_coverage",
            lambda: self.coverage.build(
                analysis_id=analysis_id,
                ticker=ticker,
                fiscal_years=years,
                sec_manifest=sec_manifest,
                company_facts=company_facts,
            ),
        )
        statements = timed(
            "validate_prefilled_statements",
            lambda: self.statements.validate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                company_facts=company_facts,
            ),
        )
        pe10 = timed(
            "pe10_e10_ten_year",
            lambda: self.pe10.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                custom_run_path=custom_run_path,
                fiscal_years=years,
                live_price=live_price,
            ),
        )
        tax = timed(
            "tax_ten_year",
            lambda: self.tax.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                company_facts=company_facts,
                year_inputs=tax_year_inputs,
            ),
        )
        rd_decision = timed(
            "rd_useful_life_decision",
            lambda: self.rd.select_useful_life(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                company_facts=company_facts,
                sec_manifest=sec_manifest,
                override=(rd_override or {}).get("life"),
                override_reason=(rd_override or {}).get("reason"),
            ),
        )
        extra_lookback = []
        if rd_decision.selected_useful_life and years:
            first = _fy_int(years[0])
            earliest = first - (rd_decision.selected_useful_life - 1)
            extra_lookback = [f"FY{y}" for y in range(earliest, first) if f"FY{y}" not in years]
            if extra_lookback:
                coverage = self.coverage.build(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    fiscal_years=years,
                    sec_manifest=sec_manifest,
                    company_facts=company_facts,
                    extra_lookback_years=extra_lookback,
                )
        rd = timed(
            "rd_history_and_capitalization",
            lambda: self.rd.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                decision=rd_decision,
                company_facts=company_facts,
            ),
        )
        leases = timed(
            "leases_ten_year_and_rate",
            lambda: self.leases.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                company_facts=company_facts,
                wacc=wacc,
                after_tax_cost_of_debt=after_tax_cost_of_debt,
                treasury_yield=treasury_yield,
            ),
        )
        lease_review = leases.review
        persisted = self._load_persisted_lease_review(analysis_id)
        if persisted is not None:
            lease_review = persisted
            if not persisted.blocking:
                applied = (
                    persisted.selected_rate
                    if persisted.selected_rate is not None
                    else persisted.approved_rate
                )
                if applied is not None:
                    self.leases._write_rate(working_path, applied)
                notes = self.leases.write_decision_notes(working_path, lease_review)
                lease_review = lease_review.model_copy(update={"notes_written": notes})
            leases = leases.model_copy(update={"review": lease_review})
        elif lease_review_override:
            # Programmatic approve is ignored; it is not a human override.
            del lease_review_override

        buybacks = timed(
            "buybacks_ten_year",
            lambda: self.buybacks.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                company_facts=company_facts,
                sec_manifest=sec_manifest,
                cache_dir=self.output_service.analysis_output_dir(analysis_id) / "sec_cache",
            ),
        )
        # Put cost of revenue on the company's latest definition (flagged cells; skipped unless totals reconcile).
        _sec_cache = self.output_service.analysis_output_dir(analysis_id) / "sec_cache"
        _filing_dirs = sorted(_sec_cache.glob("*/filings"))
        cost_recast = timed(
            "cost_of_revenue_recast",
            lambda: self.cost_recast.apply(workbook_path=working_path, filings_dir=_filing_dirs[0] if _filing_dirs else None),
        )
        current_refresh = self.current.apply(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=working_path,
            custom_run_path=custom_run_path,
            live_price=live_price,
        )
        refresh_entries = getattr(current_refresh, "entries", None)
        if not isinstance(refresh_entries, (list, tuple)):
            refresh_entries = []
        refresh_missing = getattr(current_refresh, "missing_required", None)
        if not isinstance(refresh_missing, (list, tuple)):
            refresh_missing = []
        current = NewCompanyCurrentDataReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fields=[
                CurrentDataAsOf(
                    field=getattr(e, "target_label", None) or getattr(e, "target_cell", ""),
                    value=getattr(e, "written_value", None),
                    as_of_date=getattr(e, "as_of_date", None) or getattr(e, "as_of", None),
                    source=getattr(e, "source_kind", None),
                    cell=getattr(e, "target_cell", None),
                )
                for e in refresh_entries
            ],
            as_of_mismatch=False,
            warnings=list(refresh_missing),
            summary=getattr(current_refresh, "summary", None) or "current data refresh",
        )
        as_ofs = {f.as_of_date for f in current.fields if f.as_of_date}
        if len(as_ofs) > 1:
            current.as_of_mismatch = True
            current.warnings.append("CURRENT_DATA_AS_OF_DATE_MISMATCH")

        mapped_wacc, mapped_wacc_src = (wacc, "custom_run.assumptions.wacc") if wacc is not None else resolve_workbook_wacc(working_path)
        quarterly_presentation = None
        if quarterly_analysis_required("new_company", periods.latest_quarter):
            quarterly_presentation = timed(
                "quarterly_statement_completion",
                lambda: self.quarterly_presentation.plan_and_apply(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    source_workbook_path=working_path,
                    destination_workbook_path=working_path,
                    company_facts=company_facts,
                    already_copied=True,
                ),
            )
        seasonality = timed(
            "seasonality",
            lambda: self.seasonality.project(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                latest_quarter=periods.latest_quarter,
                company_facts=company_facts,
                latest_quarter_fiscal_year=periods.latest_quarter_fiscal_year,
            ),
        )
        projection = timed(
            "projected_roic_roce",
            lambda: self.projection.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                latest_quarter=periods.latest_quarter,
                seasonality=seasonality,
                wacc=mapped_wacc,
                wacc_source=mapped_wacc_src if mapped_wacc is not None else None,
            ),
        )
        self.guard.inspect(analysis_id=analysis_id, ticker=ticker, workbook_path=working_path)

        awaiting = bool(
            lease_review
            and lease_review.blocking
            and lease_review.status == "LEASE_RATE_REVIEW_PENDING"
        )
        workflow = (
            NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
            if awaiting
            else NewCompanyWorkflowState.PROCESSING
        )

        recalc = None
        valuation = None
        val_report = None
        er_rep = None
        judgment = None
        circular = None
        analytical = None
        gate = None
        deliv = None
        if not awaiting:
            if finalize:
                workflow = NewCompanyWorkflowState.RECALCULATING
            recalc = timed(
                "excel_recalculation",
                lambda: self.excel_recalc.recalculate(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    workbook_path=working_path,
                    fiscal_year=years[-1] if years else None,
                ),
            )
            fy_int = _fy_int(years[-1]) if years else 0
            if genuine_excel_com_recalc(recalc):
                val_pack = timed(
                    "valuation_judgment",
                    lambda: self.valuation_judgment.apply(
                        analysis_id=analysis_id,
                        ticker=ticker,
                        workbook_path=working_path,
                        previous_workbook_path=template_path,
                        template_path=template_path,
                        company_facts=company_facts,
                        sec_manifest=sec_manifest,
                        fiscal_year=fy_int or None,
                        fiscal_quarter=periods.latest_quarter,
                        cache_dir=self.output_service.analysis_output_dir(analysis_id),
                        skip_initial_recalc=True,
                        prior_recalc=recalc,
                    ),
                )
                val_report, er_rep, judgment, circular, recalc_post, analytical = val_pack
                if recalc_post is not None:
                    recalc = recalc_post
                mapped_wacc, mapped_wacc_src = (
                    (wacc, "custom_run.assumptions.wacc")
                    if wacc is not None
                    else resolve_workbook_wacc(working_path)
                )
                projection = timed(
                    "projected_roic_roce_after_com",
                    lambda: self.projection.apply(
                        analysis_id=analysis_id,
                        ticker=ticker,
                        workbook_path=working_path,
                        fiscal_years=years,
                        latest_quarter=periods.latest_quarter,
                        seasonality=seasonality,
                        wacc=mapped_wacc,
                        wacc_source=mapped_wacc_src if mapped_wacc is not None else None,
                    ),
                )
            pe_fy = next((o.value for o in reversed(pe10.fiscal_year_pe10) if o.value is not None), None)
            pe_fy_label = years[-1] if years else None
            pe_fy_asof = next((o.as_of_date for o in reversed(pe10.fiscal_year_pe10) if o.as_of_date), None)
            valuation = timed(
                "valuation_extract",
                lambda: self.valuation_extract.extract(
                    working_path,
                    recalculation_complete=genuine_excel_com_recalc(recalc),
                    pe10_fiscal=pe_fy,
                    pe10_fiscal_label=pe_fy_label,
                    pe10_fiscal_as_of=pe_fy_asof,
                    pe10_current=pe10.current_pe10.value if pe10.current_pe10 else None,
                    pe10_current_as_of=pe10.current_pe10.as_of_date if pe10.current_pe10 else None,
                ),
            )
            gate = timed(
                "output_gates",
                lambda: self.gates.evaluate(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    periods=periods,
                    coverage=coverage,
                    statements=statements,
                    pe10=pe10,
                    tax=tax,
                    rd_decision=rd_decision,
                    rd=rd,
                    leases=leases,
                    lease_review=lease_review,
                    buybacks=buybacks,
                    current=current,
                    projection=projection,
                    recalc=recalc,
                    valuation=valuation,
                    valuation_judgment=val_report,
                    quarterly_unresolved_dependencies=(
                        quarterly_presentation.unresolved_dependencies
                        if quarterly_presentation is not None
                        else None
                    ),
                    quarterly_statement_blockers=(
                        list(quarterly_presentation.input_blockers)
                        if quarterly_presentation is not None
                        else None
                    ),
                    data_unavailable_flags=list(statements.flagged_missing)
                    + (list(quarterly_presentation.flagged_missing) if quarterly_presentation is not None else []),
                ),
            )
            authorized = gate.report_authorized
            deliv = timed(
                "deliverables",
                lambda: self.deliverables.produce(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    company=company,
                    fiscal_year=(
                        int("".join(ch for ch in str(periods.latest_quarter_fiscal_year) if ch.isdigit()) or fy_int)
                        if quarter_incorporated(quarterly_presentation) and periods.latest_quarter_fiscal_year
                        else fy_int
                    ),
                    completed_workbook_path=working_path,
                    output_dir=self.output_service.analysis_output_dir(analysis_id),
                    periods=periods,
                    tax=tax,
                    pe10=pe10,
                    rd_decision=rd_decision,
                    rd=rd,
                    leases=leases,
                    lease_review=lease_review,
                    buybacks=buybacks,
                    projection=projection,
                    seasonality=seasonality,
                    valuation=valuation,
                    gate=gate,
                    authorized=authorized,
                    statement_summary=statements.summary,
                    judgment=judgment,
                    valuation_report=val_report,
                    fiscal_quarter=(
                        periods.latest_quarter
                        if quarter_incorporated(quarterly_presentation)
                        else None
                    ),
                ),
            )
            if authorized and genuine_excel_com_recalc(recalc):
                workflow = NewCompanyWorkflowState.COMPLETE
            elif gate.status == "AWAITING_ANALYST_REVIEW":
                workflow = NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
            else:
                workflow = NewCompanyWorkflowState.NEEDS_REVIEW

        artifacts = {
            "workbook_structure.json": {"fiscal_years": years, "latest_quarter": periods.latest_quarter},
            "ten_year_source_coverage.json": coverage,
            "new_company_discrepancy_report.json": {
                "analysis_id": analysis_id,
                "corrections": [c.model_dump() for c in statements.corrections],
                "filled_missing": [c.model_dump() for c in statements.filled_missing],
                "discrepancies": [c.model_dump() for c in statements.discrepancies],
            },
            "new_company_tax_report.json": tax,
            "rd_useful_life_decision.json": rd_decision,
            "new_company_rd_report.json": rd,
            "new_company_lease_report.json": leases,
            "lease_rate_review.json": lease_review,
            "new_company_buyback_report.json": buybacks,
            "new_company_cost_recast_report.json": cost_recast,
            "seasonality_projection_report.json": seasonality,
            "new_company_pe10_report.json": pe10,
            "new_company_statement_validation_report.json": statements,
            "new_company_period_report.json": periods,
            "new_company_current_data_report.json": current,
            "new_company_projection_report.json": projection,
        }
        if quarterly_presentation is not None:
            artifacts["quarterly_presentation_report.json"] = quarterly_presentation
        if gate is not None:
            artifacts["new_company_output_gate_report.json"] = gate
        if valuation is not None:
            artifacts["new_company_valuation_extract_report.json"] = valuation
        if recalc is not None:
            artifacts["new_company_excel_recalc_report.json"] = {
                "status": recalc.status,
                "method": recalc.method,
                "cells_checked": recalc.cells_checked,
                "missing_cached_values": recalc.missing_cached_values,
                "formula_errors": recalc.formula_errors,
                "error": recalc.error,
                "summary": recalc.summary,
                "com_invoked": recalc.com_invoked,
            }
        if deliv is not None:
            artifacts["new_company_deliverables_report.json"] = deliv
        if val_report is not None:
            artifacts["new_company_valuation_report.json"] = val_report
        if judgment is not None:
            artifacts["new_company_analyst_judgment_report.json"] = judgment
        if circular is not None:
            artifacts["new_company_circular_reference_report.json"] = circular
        if er_rep is not None:
            artifacts["new_company_expected_return_report.json"] = er_rep
        if analytical is not None:
            artifacts["new_company_analytical_research_report.json"] = analytical
        if judgment is not None and getattr(judgment, "oe_base_analysis", None) is not None:
            artifacts["new_company_normalized_base_report.json"] = judgment.oe_base_analysis
        for name, obj in artifacts.items():
            self.output_service.write_json(analysis_id, name, obj)

        cert = _certification_status(workflow, lease_review, recalc, gate)
        state = NewCompanyRunState(
            analysis_id=analysis_id,
            ticker=ticker,
            workflow_state=workflow,
            fiscal_years=years,
            latest_quarter=periods.latest_quarter,
            workbook_path=str(working_path),
            custom_run_path=str(custom_run_path) if custom_run_path else None,
            lease_rate_approved=bool(lease_review and lease_review.decision_class == "ANALYST_OVERRIDE"),
            lease_rate_selected=bool(
                lease_review
                and not lease_review.blocking
                and (lease_review.selected_rate is not None or lease_review.proposed_rate is not None)
            ),
            rd_life_overridden=bool(rd_decision.analyst_override),
            phases_completed=[t["stage"] for t in timings],
            certification_status=cert,
            summary=f"New Company {workflow.value} cert={cert} in {(time.perf_counter()-t0):.1f}s.",
        )
        self._record_assumption_provenance(analysis_id, lease_review, rd_decision)
        self.output_service.write_json(analysis_id, "new_company_run_state.json", state)
        self.output_service.write_json(
            analysis_id,
            "new_company_certification_status.json",
            {
                "analysis_id": analysis_id,
                "ticker": ticker,
                "workflow_state": workflow.value,
                "certification_status": cert,
                "lease_rate_approved": bool(
                    lease_review and lease_review.decision_class == "ANALYST_OVERRIDE"
                ),
                "lease_rate_selected": bool(
                    lease_review
                    and not lease_review.blocking
                    and (lease_review.selected_rate is not None or lease_review.proposed_rate is not None)
                ),
                "lease_decision_class": lease_review.decision_class if lease_review else None,
                "com_invoked": bool(recalc.com_invoked) if recalc is not None else False,
                "recalc_status": recalc.status if recalc is not None else None,
                "recalc_method": recalc.method if recalc is not None else None,
                "valuation_judgment_status": val_report.status if val_report is not None else None,
                "er_decision": val_report.er_decision if val_report is not None else None,
                "oe_decision": val_report.oe_decision if val_report is not None else None,
                "graham_decision": val_report.graham_decision if val_report is not None else None,
                "original_assumptions_preserved": (
                    val_report.original_assumptions_preserved if val_report is not None else None
                ),
                "hap_introduced_circular_count": (
                    val_report.hap_introduced_circular_count if val_report is not None else None
                ),
            },
        )
        self.output_service.write_json(
            analysis_id,
            "new_company_timing_report.json",
            {"analysis_id": analysis_id, "stages": timings, "total_s": time.perf_counter() - t0},
        )
        return {
            "workflow_state": workflow,
            "periods": periods,
            "coverage": coverage,
            "statements": statements,
            "pe10": pe10,
            "tax": tax,
            "rd_decision": rd_decision,
            "rd": rd,
            "leases": leases,
            "lease_review": lease_review,
            "buybacks": buybacks,
            "current": current,
            "seasonality": seasonality,
            "projection": projection,
            "recalc": recalc,
            "valuation": valuation,
            "valuation_judgment": val_report,
            "judgment": judgment,
            "circular": circular,
            "output_gate": gate,
            "deliverables": deliv,
            "state": state,
            "timings": timings,
            "certification_status": cert,
        }

    def _load_persisted_lease_review(self, analysis_id: str) -> LeaseRateReview | None:
        try:
            raw = self.output_service.read_json(analysis_id, "lease_rate_review.json")
        except FileNotFoundError:
            return None
        try:
            return LeaseRateReview.model_validate(raw)
        except Exception:  # noqa: BLE001
            return None

    def _record_assumption_provenance(self, analysis_id: str, lease_review, rd_decision) -> None:
        notes = {
            "analysis_id": analysis_id,
            "lease": {
                "selected_rate": getattr(lease_review, "selected_rate", None) if lease_review else None,
                "classification": getattr(lease_review, "classification", None) if lease_review else None,
                "decision_class": getattr(lease_review, "decision_class", None) if lease_review else None,
                "methodology": (
                    lease_review.proposal.methodology
                    if lease_review and lease_review.proposal
                    else None
                ),
                "evidence": list(lease_review.supporting_evidence) if lease_review else [],
                "limitations": (
                    lease_review.proposal.limitations
                    if lease_review and lease_review.proposal
                    else None
                ),
                "notes_written": list(lease_review.notes_written) if lease_review else [],
                "audit_trail": list(lease_review.audit_trail) if lease_review else [],
            },
            "rd": {
                "selected_useful_life": rd_decision.selected_useful_life if rd_decision else None,
                "decision_class": (
                    "ANALYST_OVERRIDE"
                    if rd_decision and rd_decision.analyst_override is not None
                    else "AUTONOMOUS_AGENT_DECISION"
                ),
                "rationale": rd_decision.rationale if rd_decision else None,
                "evidence": list(rd_decision.company_evidence) if rd_decision else [],
                "industry_evidence": list(rd_decision.industry_evidence) if rd_decision else [],
                "citations": list(rd_decision.filing_citations) if rd_decision else [],
                "limitations": list(rd_decision.blocking_reasons) if rd_decision else [],
                "audit_trail": list(rd_decision.audit_trail) if rd_decision else [],
            },
        }
        self.output_service.write_json(analysis_id, "new_company_assumption_notes.json", notes)
        try:
            raw = self.output_service.read_json(analysis_id, "provenance_report.json")
        except FileNotFoundError:
            return
        entries = list(raw.get("entries") or [])
        if lease_review and lease_review.selected_rate is not None:
            entries.append(
                {
                    "cell_ref": "Leases!rate",
                    "worksheet": "Leases",
                    "cell": "HAP_ANALYSIS",
                    "concept": "long_term_lease_discount_rate",
                    "period": (
                        lease_review.proposal.source_fiscal_year if lease_review.proposal else ""
                    ) or "",
                    "value": lease_review.selected_rate,
                    "status": "filled",
                    "source_document": (
                        lease_review.proposal.source_accession if lease_review.proposal else None
                    ),
                    "filing_type": (
                        lease_review.proposal.source_form if lease_review.proposal else None
                    ),
                    "reasoning": lease_review.summary,
                    "write_decision": lease_review.decision_class,
                }
            )
        if rd_decision and rd_decision.selected_useful_life is not None:
            entries.append(
                {
                    "cell_ref": "R&D!B8",
                    "worksheet": "R&D",
                    "cell": "B8",
                    "concept": "rd_useful_life_years",
                    "period": "assumption",
                    "value": rd_decision.selected_useful_life,
                    "status": "filled",
                    "reasoning": rd_decision.rationale,
                    "write_decision": (
                        "ANALYST_OVERRIDE"
                        if rd_decision.analyst_override is not None
                        else "AUTONOMOUS_AGENT_DECISION"
                    ),
                }
            )
        raw["entries"] = entries
        raw["filled_count"] = int(raw.get("filled_count") or 0) + (
            (1 if lease_review and lease_review.selected_rate is not None else 0)
            + (1 if rd_decision and rd_decision.selected_useful_life is not None else 0)
        )
        self.output_service.write_json(analysis_id, "provenance_report.json", raw)
