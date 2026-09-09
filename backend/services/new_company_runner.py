"""New Company initiation runner — ten-year coverage, analyst lease-rate checkpoint, Word."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from models.new_company import (
    NewCompanyCurrentDataReport,
    NewCompanyRunState,
    NewCompanyWorkflowState,
    CurrentDataAsOf,
)
from services.annual_formula_guard_service import AnnualFormulaGuardService
from services.annual_valuation_extract_service import AnnualValuationExtractService
from services.current_data_refresh_service import CurrentDataRefreshService
from services.excel_recalc_service import ExcelRecalcService
from services.new_company_buyback_service import NewCompanyBuybackService
from services.new_company_deliverables_service import NewCompanyDeliverablesService
from services.new_company_lease_service import NewCompanyLeaseService
from services.new_company_output_gate_service import NewCompanyOutputGateService
from services.new_company_pe10_service import NewCompanyPe10Service
from services.new_company_period_service import NewCompanyPeriodService
from services.new_company_projection_service import NewCompanyProjectionService
from services.new_company_rd_service import NewCompanyRdService
from services.new_company_seasonality_service import NewCompanySeasonalityService
from services.new_company_sec_coverage_service import NewCompanySecCoverageService
from services.new_company_statement_validation_service import NewCompanyStatementValidationService
from services.new_company_tax_service import NewCompanyTaxService
from services.output_service import OutputService


def _fy_int(token: str | None) -> int:
    digits = "".join(ch for ch in str(token or "") if ch.isdigit())
    return int(digits) if digits else 0


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
        self.seasonality = NewCompanySeasonalityService()
        self.projection = NewCompanyProjectionService()
        self.gates = NewCompanyOutputGateService()
        self.deliverables = NewCompanyDeliverablesService()
        self.valuation_extract = AnnualValuationExtractService()
        self.excel_recalc = ExcelRecalcService()
        self.guard = AnnualFormulaGuardService()
        self.current = CurrentDataRefreshService()

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
        if lease_review_override:
            lease_review = self.leases.apply_review(
                lease_review,
                action=str(lease_review_override.get("action") or "approve"),
                rate=lease_review_override.get("rate"),
                reason=lease_review_override.get("reason"),
                workbook_path=working_path,
            )
            leases = leases.model_copy(update={"review": lease_review})

        buybacks = timed(
            "buybacks_ten_year",
            lambda: self.buybacks.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                company_facts=company_facts,
            ),
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
                    as_of_date=None,
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

        seasonality = timed(
            "seasonality",
            lambda: self.seasonality.project(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_years=years,
                latest_quarter=periods.latest_quarter,
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
                wacc=wacc,
            ),
        )
        self.guard.inspect(analysis_id=analysis_id, ticker=ticker, workbook_path=working_path)

        awaiting = bool(lease_review and lease_review.blocking)
        workflow = (
            NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
            if awaiting and not finalize
            else NewCompanyWorkflowState.PROCESSING
        )

        recalc = None
        valuation = None
        gate = None
        deliv = None
        if not awaiting or finalize:
            if awaiting and finalize:
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
            pe_fy = next((o.value for o in reversed(pe10.fiscal_year_pe10) if o.value is not None), None)
            pe_fy_label = years[-1] if years else None
            pe_fy_asof = next((o.as_of_date for o in reversed(pe10.fiscal_year_pe10) if o.as_of_date), None)
            valuation = timed(
                "valuation_extract",
                lambda: self.valuation_extract.extract(
                    working_path,
                    recalculation_complete=(recalc.status == "ok"),
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
                ),
            )
            authorized = gate.report_authorized
            fy_int = _fy_int(years[-1]) if years else 0
            deliv = timed(
                "deliverables",
                lambda: self.deliverables.produce(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    company=company,
                    fiscal_year=fy_int,
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
                ),
            )
            if authorized:
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
            "seasonality_projection_report.json": seasonality,
            "new_company_pe10_report.json": pe10,
            "new_company_statement_validation_report.json": statements,
            "new_company_period_report.json": periods,
            "new_company_current_data_report.json": current,
            "new_company_projection_report.json": projection,
        }
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
            }
        if deliv is not None:
            artifacts["new_company_deliverables_report.json"] = deliv
        for name, obj in artifacts.items():
            self.output_service.write_json(analysis_id, name, obj)

        state = NewCompanyRunState(
            analysis_id=analysis_id,
            ticker=ticker,
            workflow_state=workflow,
            fiscal_years=years,
            latest_quarter=periods.latest_quarter,
            workbook_path=str(working_path),
            custom_run_path=str(custom_run_path) if custom_run_path else None,
            lease_rate_approved=bool(lease_review and not lease_review.blocking),
            rd_life_overridden=bool(rd_decision.analyst_override),
            phases_completed=[t["stage"] for t in timings],
            summary=f"New Company {workflow.value} in {(time.perf_counter()-t0):.1f}s.",
        )
        self.output_service.write_json(analysis_id, "new_company_run_state.json", state)
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
            "output_gate": gate,
            "deliverables": deliv,
            "state": state,
            "timings": timings,
        }
