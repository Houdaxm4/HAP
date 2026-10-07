"""Quarterly Expected Returns / Enterprise Value parity with certified Annual Update.

Reuses Annual judgment, growth analysis, normalized-base diagnostic/disclosure,
Excel COM recalculation, and circular-reference detection. Does not overwrite
original analyst growth-rate cells or valuation formulas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models.annual_update import NormalizedEarningsPowerAnalysis
from models.quarterly_update import QuarterlyValuationReport
from services.annual_analyst_intelligence_service import AnnualAnalystIntelligenceService
from services.annual_analytical_research_service import AnnualAnalyticalResearchService
from services.annual_judgment_service import AnnualJudgmentService
from services.annual_normalized_base_disclosure_service import (
    AnnualNormalizedBaseDisclosureService,
)
from services.circular_reference_service import CircularReferenceService
from services.excel_recalc_service import ExcelRecalcService
from services.workbook_flag_service import flag_structural


def _period_context(fiscal_quarter: int | None) -> str:
    q = fiscal_quarter or 0
    if q == 1:
        return (
            "Q1: reported three-month results. Do not treat a single quarter as a full year "
            "without the established annualization/projection treatment."
        )
    if q == 2:
        return (
            "Q2: distinguish reported six-month YTD, standalone Q2, and projected full-year. "
            "Partial-year amounts must not feed annual valuation formulas without annualization."
        )
    if q == 3:
        return (
            "Q3: distinguish reported nine-month YTD, standalone Q3, and projected full-year. "
            "Partial-year amounts must not feed annual valuation formulas without annualization."
        )
    if q == 4:
        return "Q4: full-year results from the 10-K; standalone Q4 = FY - nine-month YTD."
    return "Quarterly period context unspecified."


class QuarterlyValuationService:
    """Run certified Annual ER/EV/Graham/OE-base services on a quarterly workbook."""

    def __init__(self) -> None:
        self.excel_recalc = ExcelRecalcService()
        self.intelligence = AnnualAnalystIntelligenceService()
        self.judgment = AnnualJudgmentService()
        self.analytical_research = AnnualAnalyticalResearchService()
        self.circular = CircularReferenceService()

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        previous_workbook_path: Path | None = None,
        template_path: Path | None = None,
        company_facts: dict[str, Any] | None = None,
        sec_manifest: dict[str, Any] | None = None,
        fiscal_year: int | None = None,
        fiscal_quarter: int | None = None,
        cache_dir: Path | None = None,
    ) -> tuple[QuarterlyValuationReport, Any, Any, Any, Any, Any]:
        """
        Returns (report, er_report, judgment, circular, recalc, analytical).
        HAP_ANALYSIS writes are adjacent; original assumption cells are not overwritten.
        """
        path = Path(workbook_path)
        fy_label = str(fiscal_year) if fiscal_year else None
        recalc_pre = self.excel_recalc.recalculate(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=path,
            fiscal_year=fy_label,
        )
        ctx = self.intelligence.build_judgment_context(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=path,
            company_facts=company_facts,
        )
        ctx["quarterly_period_context"] = _period_context(fiscal_quarter)
        analytical = None
        base_raw = ctx.get("oe_base_analysis")
        base_obj = None
        if isinstance(base_raw, dict):
            base_obj = NormalizedEarningsPowerAnalysis.model_validate(base_raw)
        elif hasattr(base_raw, "decision"):
            base_obj = base_raw
        if base_obj is not None:
            captured = base_obj
            analytical = self.analytical_research.investigate(
                analysis_id=analysis_id,
                ticker=ticker,
                base=captured,
                sec_manifest=sec_manifest,
                fiscal_year=fiscal_year,
                cache_dir=cache_dir,
            )
            base_obj = self.analytical_research.apply_to_diagnostic(captured, analytical)
            base_obj.disclosure = AnnualNormalizedBaseDisclosureService().build(base_obj, analytical)
            ctx["oe_base_analysis"] = base_obj.model_dump()
            ctx["analytical_research"] = analytical

        from services.valuation_correction_service import ValuationCorrectionService

        self.last_input_review = None
        try:
            self.last_input_review = ValuationCorrectionService().apply(path, company_facts)
        except Exception:  # noqa: BLE001 - advisory: never stops the run
            self.last_input_review = None
        if self.last_input_review is not None and self.last_input_review.applied:
            self.excel_recalc.recalculate(analysis_id=analysis_id, ticker=ticker, workbook_path=path, fiscal_year=fy_label)
        self.judgment.input_review = self.last_input_review
        er_rep, judge = self.judgment.apply(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=path,
            context=ctx,
        )
        circular = self.circular.classify_against_source(
            analysis_id=analysis_id,
            ticker=ticker,
            current_path=path,
            source_path=previous_workbook_path,
            template_path=template_path,
        )
        if circular.pre_existing or circular.hap_introduced:
            from openpyxl import load_workbook as _lw_circ

            _cwb = _lw_circ(path)
            try:
                for cycle in list(circular.pre_existing) + list(circular.hap_introduced):
                    for ref in cycle.cells:
                        if "!" not in ref:
                            continue
                        sh, addr = ref.split("!", 1)
                        if sh in _cwb.sheetnames:
                            flag_structural(_cwb[sh], addr, cycle=cycle.cells)
                _cwb.save(path)
            finally:
                _cwb.close()

        recalc = self.excel_recalc.recalculate(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=path,
            fiscal_year=fy_label,
        )
        _ = recalc_pre

        er_d = getattr(getattr(judge, "er_analysis", None), "decision", None) or getattr(
            getattr(judge, "expected_return", None), "decision", None
        )
        oe_d = getattr(getattr(judge, "oe_analysis", None), "decision", None)
        gr_d = getattr(getattr(judge, "graham_analysis", None), "decision", None)
        base_d = None
        oe_base = getattr(judge, "oe_base_analysis", None) or ctx.get("oe_base_analysis")
        if oe_base is not None:
            base_d = getattr(oe_base, "decision", None) or (
                oe_base.get("decision") if isinstance(oe_base, dict) else None
            )
        hap_n = len(circular.hap_introduced)
        status = "ok"
        if hap_n:
            status = "BLOCKING_STRUCTURAL_ERROR"
        elif circular.status == "PRE_EXISTING_REVIEW":
            status = "PRE_EXISTING_REVIEW"
        summary = (
            f"Quarterly valuation (Annual parity): ER={er_d} OE={oe_d} Graham={gr_d} "
            f"OE-base={base_d}; original assumptions preserved; "
            f"recalc={recalc.status} circular={circular.status}. "
            f"{_period_context(fiscal_quarter)}"
        )
        report = QuarterlyValuationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            status=status,
            fiscal_quarter=fiscal_quarter,
            fiscal_year=fiscal_year,
            period_context=_period_context(fiscal_quarter),
            original_assumptions_preserved=True,
            excel_recalc_status=recalc.status,
            excel_recalc_method=recalc.method,
            circular_status=circular.status,
            hap_introduced_circular_count=hap_n,
            judgment_summary=getattr(judge, "summary", "") or "",
            er_decision=er_d,
            oe_decision=oe_d,
            graham_decision=gr_d,
            normalized_base_decision=base_d,
            summary=summary,
        )
        return report, er_rep, judge, circular, recalc, analytical
