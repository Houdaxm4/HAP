"""HAP_ANALYSIS for Expected Return, Owner Earnings, and Graham — never population."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.annual_update import (
    AnnualAnalystJudgmentReport,
    AnnualExpectedReturnReport,
    AnalyticalResearchReport,
    DISCLOSE_DISTORTED_BASE,
    JudgmentRecord,
    NormalizedBaseDisclosure,
    NormalizedEarningsPowerAnalysis,
    ValuationAssumptionAnalysis,
)
from models.write_actions import WriteActionClass
from services.formula_utils import is_formula
from services.hap_analysis_layout_service import HapAnalysisLayoutService

_BV_DEFAULT = "BOOK_VALUE_GROWTH"
_EPS_ALT = "EPS_GROWTH"
ER_SHEET = "Expected Returns & Buybacks"
EV_SHEET = "Enterprise Value"


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _rewrite_er_formula(
    formula: str,
    *,
    g_cell: str,
    roe_cell: str,
    bv_col: int,
    eps_col: int,
    map_b5_to_g: bool = False,
) -> str:
    """Remap growth/BV/EPS refs while preserving ROE as ROE."""
    from openpyxl.utils import get_column_letter

    from services.formula_utils import parse_cell_refs

    pieces: list[str] = []
    last = 0
    for ref in parse_cell_refs(formula):
        pieces.append(formula[last : ref["start"]])
        sheet = ref["sheet"]
        col, row = ref["col"], ref["row"]
        token = None
        if sheet is None and col == 1 and row == 11:
            token = g_cell
        elif sheet is None and col == 1 and row == 14:
            token = roe_cell
        elif map_b5_to_g and sheet is None and col == 2 and row == 5:
            token = g_cell
        elif map_b5_to_g and sheet and "EXPECTED RETURNS" in sheet.upper() and col == 2 and row == 5:
            token = g_cell
        elif sheet is None and col == 3 and 17 <= row <= 26:
            abs_c = "$" if ref["col_abs"] else ""
            abs_r = "$" if ref["row_abs"] else ""
            token = f"{abs_c}{get_column_letter(bv_col)}{abs_r}{row}"
        elif sheet is None and col == 4 and 17 <= row <= 26:
            abs_c = "$" if ref["col_abs"] else ""
            abs_r = "$" if ref["row_abs"] else ""
            token = f"{abs_c}{get_column_letter(eps_col)}{abs_r}{row}"
        if token is None:
            token = ref["text"]
        pieces.append(token)
        last = ref["end"]
    pieces.append(formula[last:])
    return "".join(pieces)


def _analysis(ctx: dict[str, Any], key: str) -> ValuationAssumptionAnalysis | None:
    raw = ctx.get(key)
    if isinstance(raw, ValuationAssumptionAnalysis):
        return raw
    if isinstance(raw, dict) and raw.get("metric"):
        try:
            return ValuationAssumptionAnalysis.model_validate(raw)
        except Exception:
            return None
    return None


def _base_analysis(ctx: dict[str, Any]) -> NormalizedEarningsPowerAnalysis | None:
    raw = ctx.get("oe_base_analysis")
    if isinstance(raw, NormalizedEarningsPowerAnalysis):
        base = raw
    elif isinstance(raw, dict) and raw.get("metric"):
        try:
            base = NormalizedEarningsPowerAnalysis.model_validate(raw)
        except Exception:
            return None
    else:
        return None
    if base.disclosure is None:
        research = ctx.get("analytical_research")
        if isinstance(research, dict):
            try:
                research = AnalyticalResearchReport.model_validate(research)
            except Exception:
                research = None
        from services.annual_normalized_base_disclosure_service import (
            AnnualNormalizedBaseDisclosureService,
        )

        base.disclosure = AnnualNormalizedBaseDisclosureService().build(base, research)
    return base


def _judgment_from_analysis(
    analysis: ValuationAssumptionAnalysis,
    *,
    original_methodology: str,
    workbook_impact: str,
    model_impact: str,
) -> JudgmentRecord:
    adjusted = analysis.decision == "ADJUST"
    if analysis.decision == "KEEP_EXISTING":
        change = "ACCEPTED"
        selected_method = original_methodology
        selected = analysis.existing_assumption
    elif analysis.decision == "ADJUST":
        change = "NORMALIZED"
        selected_method = analysis.selection_method or "evidence_backed_rate"
        selected = analysis.selected_prospective_rate
    else:
        change = "INSUFFICIENT_EVIDENCE"
        selected_method = analysis.selection_method or "no_alternative_rate"
        selected = analysis.existing_assumption
    return JudgmentRecord(
        metric=analysis.metric,
        original_value=analysis.existing_assumption,
        selected_value=selected,
        original_methodology=original_methodology,
        selected_methodology=selected_method,
        reasonableness_classification=analysis.decision,
        historical_evidence=analysis.historical_observations,
        qualitative_evidence=analysis.evidence,
        evidence=analysis.evidence,
        rationale=analysis.rationale,
        workbook_impact=workbook_impact,
        model_impact=model_impact,
        change_type=change,
        source_references=analysis.provenance,
        confidence=analysis.confidence,
        adjusted=adjusted,
        decision=analysis.decision,
        existing_assumption_source=analysis.existing_assumption_source,
        existing_assumption_grain=analysis.existing_assumption_grain,
        actual_formula_driver=analysis.actual_formula_driver,
        normalization_adjustments=analysis.normalization_adjustments,
        distortions_identified=analysis.distortions_identified,
        prospective_range_low=analysis.prospective_range_low,
        prospective_range_high=analysis.prospective_range_high,
        selection_method=analysis.selection_method,
        anomalies=analysis.anomalies,
        evidence_center=analysis.evidence_center,
        evidence_dispersion=analysis.evidence_dispersion,
        existing_distance_from_evidence=analysis.existing_distance_from_evidence,
        materiality_assessment=analysis.materiality_assessment,
        decision_basis=analysis.decision_basis,
    )


class AnnualJudgmentService:
    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        context: dict[str, Any] | None = None,
    ) -> tuple[AnnualExpectedReturnReport, AnnualAnalystJudgmentReport]:
        ctx = context or {}
        er_a = _analysis(ctx, "er_analysis")
        oe_a = _analysis(ctx, "oe_analysis")
        gr_a = _analysis(ctx, "graham_analysis")
        if er_a and oe_a and gr_a:
            return self._apply_from_analyses(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=workbook_path,
                ctx=ctx,
                er_a=er_a,
                oe_a=oe_a,
                gr_a=gr_a,
            )
        return self._apply_legacy_context(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=workbook_path,
            ctx=ctx,
        )

    def refresh_parallel_expected_return(
        self,
        *,
        workbook_path: Path,
        er_report: AnnualExpectedReturnReport,
        judgment: AnnualAnalystJudgmentReport,
        recalc_ok: bool,
    ) -> None:
        """Read COM-cached HAP Expected Return. ADJUST requires a real parallel E14."""
        cell = er_report.hap_expected_return_cell
        rec = judgment.expected_return
        er_a = judgment.er_analysis
        if rec is None or rec.decision != "ADJUST":
            return
        value = None
        if cell and "!" in cell and recalc_ok:
            sheet, addr = cell.split("!", 1)
            wb = load_workbook(workbook_path, data_only=True)
            try:
                if sheet in wb.sheetnames:
                    value = _num(wb[sheet][addr].value)
            finally:
                wb.close()
        if value is None:
            rec.decision = "INSUFFICIENT_EVIDENCE"
            rec.change_type = "INSUFFICIENT_EVIDENCE"
            rec.adjusted = False
            rec.parallel_model_status = "recalc_incomplete" if not recalc_ok else "incoherent"
            rec.rationale = (
                (rec.rationale or "")
                + " HAP cannot certify ADJUST without a calculated parallel Expected Return. "
                "INSUFFICIENT_EVIDENCE."
            ).strip()
            er_report.reasonableness = "INSUFFICIENT_EVIDENCE"
            er_report.parallel_model_status = rec.parallel_model_status
            er_report.final_expected_return = None
            er_report.hap_expected_return = None
            if er_a is not None:
                er_a.decision = "INSUFFICIENT_EVIDENCE"
                er_a.selected_prospective_rate = None
            return
        rec.hap_expected_return = value
        rec.parallel_model_status = "calculated"
        er_report.hap_expected_return = value
        er_report.final_expected_return = value
        er_report.parallel_model_status = "calculated"

    def _apply_from_analyses(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        ctx: dict[str, Any],
        er_a: ValuationAssumptionAnalysis,
        oe_a: ValuationAssumptionAnalysis,
        gr_a: ValuationAssumptionAnalysis,
    ) -> tuple[AnnualExpectedReturnReport, AnnualAnalystJudgmentReport]:
        er_rec = _judgment_from_analysis(
            er_a,
            original_methodology=_BV_DEFAULT,
            workbook_impact="HAP_ANALYSIS beside Expected Return; original B5/D17:D26 unchanged",
            model_impact="Expected Return terminal value trajectory",
        )
        oe_rec = _judgment_from_analysis(
            oe_a,
            original_methodology="annualized_oe_forecast_driver",
            workbook_impact="HAP_ANALYSIS beside Enterprise Value; original OE assumption unchanged",
            model_impact="20-year Owner Earnings DCF trajectory",
        )
        gr_rec = _judgment_from_analysis(
            gr_a,
            original_methodology="graham_eps_growth_input",
            workbook_impact="HAP_ANALYSIS beside Graham; original formula/entry price unchanged",
            model_impact="Graham intrinsic value and entry price",
        )
        er_change = er_rec.change_type or "ACCEPTED"
        oe_change = oe_rec.change_type or "ACCEPTED"
        eps_change = gr_rec.change_type or "ACCEPTED"
        hap_cells, preserved, er_parallel = self._write_hap_analysis(
            workbook_path,
            er_change=er_change,
            er_original=er_a.existing_assumption,
            er_hap=er_a.selected_prospective_rate if er_a.decision == "ADJUST" else None,
            er_reason=er_a.rationale,
            oe_change=oe_change,
            oe_original=oe_a.existing_assumption,
            oe_hap=oe_a.selected_prospective_rate if oe_a.decision == "ADJUST" else None,
            oe_reason=oe_a.rationale,
            eps_change=eps_change,
            eps_original=gr_a.existing_assumption,
            eps_hap=gr_a.selected_prospective_rate if gr_a.decision == "ADJUST" else None,
            eps_reason=gr_a.rationale,
            er_analysis=er_a,
            oe_base_disclosure=(_base_analysis(ctx).disclosure if _base_analysis(ctx) else None),
        )
        if er_a.decision == "ADJUST" and not er_parallel.get("coherent"):
            er_a.decision = "INSUFFICIENT_EVIDENCE"
            er_a.selected_prospective_rate = None
            er_a.selection_method = "insufficient_evidence_cannot_construct_parallel_expected_return"
            er_a.decision_basis = (
                "HAP cannot construct a coherent parallel Expected Return that preserves "
                "retention, ROE, sustainable growth, and E14 semantics. "
                f"{er_parallel.get('failure_reason') or ''} INSUFFICIENT_EVIDENCE is preferred "
                "to a mathematically convenient clone."
            )
            er_a.rationale = (er_a.rationale + " " + er_a.decision_basis).strip()
            er_rec = _judgment_from_analysis(
                er_a,
                original_methodology=_BV_DEFAULT,
                workbook_impact="HAP_ANALYSIS beside Expected Return; original B5/D17:D26 unchanged",
                model_impact="Expected Return terminal value trajectory",
            )
            er_rec.parallel_model_status = "incoherent"
            er_rec.semantic_substitution = er_parallel.get("substitution")
        else:
            er_rec.hap_expected_return_cell = er_parallel.get("hap_er_cell")
            er_rec.semantic_substitution = er_parallel.get("substitution")
            er_rec.parallel_model_status = er_parallel.get("status")
        er_report = AnnualExpectedReturnReport(
            analysis_id=analysis_id,
            ticker=ticker,
            default_methodology=_BV_DEFAULT,
            original_growth_rate=er_a.existing_assumption,
            original_expected_return=_num(ctx.get("expected_return")),
            reasonableness=er_a.decision,
            selected_methodology=er_rec.selected_methodology or _BV_DEFAULT,
            selected_growth_rate=er_rec.selected_value if isinstance(er_rec.selected_value, (int, float)) else _num(er_rec.selected_value),
            final_expected_return=None,
            growth_3y=oe_a.historical_observations.get("oe_3y_cagr"),
            growth_5y=gr_a.historical_observations.get("eps_5y_cagr"),
            growth_10y=gr_a.historical_observations.get("eps_10y_cagr"),
            alternative_windows={
                "er_existing": er_a.existing_assumption,
                "eps_10y": gr_a.historical_observations.get("eps_10y_cagr"),
                "eps_5y": gr_a.historical_observations.get("eps_5y_cagr"),
                "oe_annualized": oe_a.existing_assumption,
                "oe_total_change": oe_a.historical_observations.get("oe_total_change_b6"),
            },
            distortions=er_a.distortions_identified + oe_a.distortions_identified + gr_a.distortions_identified,
            evidence=er_a.evidence,
            rationale=er_a.rationale,
            confidence=er_a.confidence,
            summary=er_a.rationale,
            hap_expected_return_cell=er_parallel.get("hap_er_cell"),
            semantic_substitution=er_parallel.get("substitution"),
            original_mechanics=dict(er_a.historical_observations.get("original_mechanics") or {}),
            hap_mechanics=er_parallel.get("hap_mechanics") or {},
            parallel_model_status=er_rec.parallel_model_status,
            retention_defect_class=(er_a.historical_observations or {}).get("retention_defect_class"),
        )
        judgment = AnnualAnalystJudgmentReport(
            analysis_id=analysis_id,
            ticker=ticker,
            lease_rate=ctx.get("lease_judgment"),
            expected_return=er_rec,
            owner_earnings_growth=oe_rec,
            graham_eps_growth=gr_rec,
            hap_analysis_cells=hap_cells,
            original_cells_preserved=preserved,
            summary="HAP_ANALYSIS documented beside original valuation; originals not overwritten.",
            er_analysis=er_a,
            oe_analysis=oe_a,
            graham_analysis=gr_a,
            oe_base_analysis=_base_analysis(ctx),
        )
        return er_report, judgment

    def _apply_legacy_context(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        ctx: dict[str, Any],
    ) -> tuple[AnnualExpectedReturnReport, AnnualAnalystJudgmentReport]:
        """Preserve HAP_ANALYSIS layout tests that inject explicit context without analyses.

        Does not invent a generic 8% (or any other) fallback rate.
        """
        bv = _num(ctx.get("book_value_growth"))
        er = _num(ctx.get("expected_return"))
        oe = _num(ctx.get("owner_earnings_growth"))
        eps = _num(ctx.get("eps_growth"))
        qualitative = [str(x) for x in ctx.get("evidence") or []]
        bv_class = str(ctx.get("bv_classification") or "UNKNOWN")
        eps_class = str(ctx.get("eps_classification") or "UNKNOWN")
        oe_class = str(ctx.get("oe_classification") or "UNKNOWN")

        er_method = _BV_DEFAULT
        er_selected_g = bv
        er_reason = (
            "HAP reviewed the existing Expected Return assumption as a prospective rate. "
            "Historical EPS/BV CAGR is evidence, not automatically the forecast. "
            "Existing assumption appears consistent with the provided context; no adjustment is recommended."
        )
        er_flag = bv_class.lower() if bv_class != "UNKNOWN" else "reasonable"
        er_change = "ACCEPTED"
        injected_bv = _num(ctx.get("normalized_bv_growth"))
        if ctx.get("prefer_eps") and eps is not None:
            er_method = _EPS_ALT
            er_selected_g = eps
            er_change = "METHODOLOGY_SWITCH"
            er_flag = "DISTORTED" if bv_class == "DISTORTED" else "AGGRESSIVE"
            er_reason = (
                "1. Existing assumption is book-value growth used prospectively. "
                "2. It is a historical trajectory, not a forecast by itself. "
                "3. It is not appropriate prospectively because it is economically distorted. "
                f"4. Evidence: {'; '.join(qualitative[:4]) or 'BV vs EPS history'}. "
                f"5. HAP-adjusted prospective rate: {eps:.1%} EPS growth. "
                "6. EPS growth is more representative of forward earnings power. "
                "7. Effect: HAP Expected Return uses the EPS path beside the original. "
                "8. Uncertainty: cyclicality and one-time items remain."
            )
        elif injected_bv is not None:
            er_selected_g = injected_bv
            er_change = "NORMALIZED"
            er_flag = "DISTORTED" if bv_class == "DISTORTED" else "AGGRESSIVE"
            er_reason = (
                "Context supplied an evidence-backed replacement rate; HAP does not substitute "
                f"a generic default. HAP-adjusted prospective rate: {er_selected_g:.1%}."
            )
        elif bv_class == "CONSERVATIVE":
            er_flag = "CONSERVATIVE"
            er_reason = (
                "Existing assumption appears conservative; HAP does not automatically raise it. "
                "No adjustment recommended without stronger prospective evidence."
            )

        hist_evidence = {
            "bv_growth": bv,
            "eps_growth_10y": eps,
            "eps_growth_5y": ctx.get("eps_growth_5y"),
            "oe_growth": oe,
            "oe_growth_3y": ctx.get("owner_earnings_3y"),
            "oe_growth_5y": ctx.get("owner_earnings_5y"),
            "oe_growth_10y": ctx.get("owner_earnings_10y"),
        }
        er_report = AnnualExpectedReturnReport(
            analysis_id=analysis_id,
            ticker=ticker,
            default_methodology=_BV_DEFAULT,
            original_growth_rate=bv,
            original_expected_return=er,
            reasonableness=er_flag,
            selected_methodology=er_method,
            selected_growth_rate=er_selected_g if isinstance(er_selected_g, (int, float)) else _num(er_selected_g),
            final_expected_return=er if er_change == "ACCEPTED" else None,
            growth_3y=ctx.get("owner_earnings_3y"),
            growth_5y=ctx.get("eps_growth_5y") or ctx.get("owner_earnings_5y"),
            growth_10y=eps,
            alternative_windows={
                "bv": bv,
                "eps_10y": eps,
                "eps_5y": ctx.get("eps_growth_5y"),
                "oe_3y": ctx.get("owner_earnings_3y"),
                "oe_5y": ctx.get("owner_earnings_5y"),
                "oe_10y": ctx.get("owner_earnings_10y"),
            },
            distortions=[e for e in qualitative if "diverge" in e.lower() or "distort" in e.lower()],
            evidence=qualitative,
            rationale=er_reason,
            confidence=0.75 if er_change == "ACCEPTED" else 0.65,
            summary=er_reason,
        )

        oe_injected = _num(ctx.get("normalized_oe_growth"))
        oe_adj = oe_injected is not None
        oe_sel = oe_injected if oe_adj else oe
        oe_change = "NORMALIZED" if oe_adj else "ACCEPTED"
        oe_reason = (
            "Existing Owner Earnings growth appears consistent with the provided context; no HAP adjustment recommended."
            if not oe_adj
            else (
                "1. Existing OE growth is the workbook prospective assumption. "
                "2. It is used to extrapolate enterprise value. "
                f"3. Historical OE CAGR {oe} is not automatically the forecast. "
                f"4. Windows considered: 3y={ctx.get('owner_earnings_3y')} 5y={ctx.get('owner_earnings_5y')} "
                f"10y={ctx.get('owner_earnings_10y')}. "
                f"5. HAP-adjusted OE growth: {oe_sel} (supplied by analysis context, not a generic fallback). "
                "6. The adjusted rate is more consistent with sustainable operating earnings. "
                "7. HAP EV / Margin of Safety are shown beside originals. "
                "8. Uncertainty remains around cyclicality and one-time items."
            )
        )

        eps_injected = _num(ctx.get("normalized_eps_growth"))
        eps_adj = eps_injected is not None
        eps_sel = eps_injected if eps_adj else eps
        eps_change = "NORMALIZED" if eps_adj else "ACCEPTED"
        eps_reason = (
            "Graham assumptions appear consistent with the provided context; historical EPS 10-year "
            "growth was not automatically used as the prospective Graham growth rate. No adjustment required."
            if not eps_adj
            else (
                "1. Existing Graham growth leans on historical EPS 10-year growth. "
                "2. That metric is a historical fact (CRF/workbook), not automatically a forecast. "
                "3. It is not suitable prospectively given distortion/sustainability concerns. "
                f"4. Evidence: 10y={eps} 5y={ctx.get('eps_growth_5y')}. "
                f"5. HAP-adjusted Graham growth: {eps_sel} (supplied by analysis context, not a generic fallback). "
                "6. The adjusted rate is a more defensible prospective assumption. "
                "7. HAP Graham Entry Price is shown beside the original. "
                "8. Uncertainty: mean-reversion vs structural growth."
            )
        )

        hap_cells, preserved, _er_parallel = self._write_hap_analysis(
            workbook_path,
            er_change=er_change,
            er_original=bv,
            er_hap=er_selected_g if er_change != "ACCEPTED" else None,
            er_reason=er_reason,
            oe_change=oe_change,
            oe_original=oe,
            oe_hap=oe_sel if oe_adj else None,
            oe_reason=oe_reason,
            eps_change=eps_change,
            eps_original=eps,
            eps_hap=eps_sel if eps_adj else None,
            eps_reason=eps_reason,
            oe_base_disclosure=(_base_analysis(ctx).disclosure if _base_analysis(ctx) else None),
        )
        judgment = AnnualAnalystJudgmentReport(
            analysis_id=analysis_id,
            ticker=ticker,
            lease_rate=ctx.get("lease_judgment"),
            expected_return=JudgmentRecord(
                metric="expected_return_growth",
                original_value=bv,
                selected_value=er_selected_g,
                original_methodology=_BV_DEFAULT,
                selected_methodology=er_method,
                reasonableness_classification=er_flag,
                historical_evidence=hist_evidence,
                qualitative_evidence=qualitative,
                evidence=qualitative,
                rationale=er_reason,
                workbook_impact="HAP_ANALYSIS beside Expected Return; original B5/D17:D26 unchanged",
                model_impact="Expected Return terminal value trajectory",
                change_type=er_change,
                source_references=["workbook", "hap_analysis"],
                confidence=0.75 if er_change == "ACCEPTED" else 0.65,
                adjusted=er_change != "ACCEPTED",
                decision="ADJUST" if er_change != "ACCEPTED" else "KEEP_EXISTING",
            ),
            owner_earnings_growth=JudgmentRecord(
                metric="owner_earnings_growth",
                original_value=oe,
                selected_value=oe_sel if oe_adj else oe,
                original_methodology="historical_oe_growth",
                selected_methodology="normalized_oe_growth" if oe_adj else "historical_oe_growth",
                reasonableness_classification=oe_class,
                historical_evidence={
                    "oe_3y": ctx.get("owner_earnings_3y"),
                    "oe_5y": ctx.get("owner_earnings_5y"),
                    "oe_10y": ctx.get("owner_earnings_10y"),
                },
                qualitative_evidence=qualitative,
                evidence=qualitative,
                rationale=oe_reason,
                workbook_impact="HAP_ANALYSIS beside Enterprise Value; original OE assumption unchanged",
                model_impact="20-year Owner Earnings DCF trajectory",
                change_type=oe_change,
                source_references=["inputs_owner_earnings_series"],
                confidence=0.7,
                adjusted=oe_adj,
                decision="ADJUST" if oe_adj else "KEEP_EXISTING",
            ),
            graham_eps_growth=JudgmentRecord(
                metric="graham_eps_growth",
                original_value=eps,
                selected_value=eps_sel if eps_adj else eps,
                original_methodology="historical_eps_cagr",
                selected_methodology="normalized_eps_growth" if eps_adj else "historical_eps_cagr",
                reasonableness_classification=eps_class,
                historical_evidence={
                    "eps_10y": eps,
                    "eps_5y": ctx.get("eps_growth_5y"),
                },
                qualitative_evidence=qualitative,
                evidence=qualitative,
                rationale=eps_reason,
                workbook_impact="HAP_ANALYSIS beside Graham; original formula/entry price unchanged",
                model_impact="Graham intrinsic value and entry price",
                change_type=eps_change,
                source_references=["final_metrics_eps_cagr"],
                confidence=0.7,
                adjusted=eps_adj,
                decision="ADJUST" if eps_adj else "KEEP_EXISTING",
            ),
            hap_analysis_cells=hap_cells,
            original_cells_preserved=preserved,
            summary="HAP_ANALYSIS documented beside original valuation; originals not overwritten.",
            oe_base_analysis=_base_analysis(ctx),
        )
        return er_report, judgment

    @staticmethod
    def _oe_base_disclosure_rows(disc: NormalizedBaseDisclosure | None) -> list[tuple[str, Any]]:
        if disc is None or disc.decision != DISCLOSE_DISTORTED_BASE:
            return []
        from services.annual_normalized_base_disclosure_service import format_millions

        reported = format_millions(disc.reported_base)
        rows: list[tuple[str, Any]] = [
            ("OE BASE — ORIGINAL ANALYST VALUATION", f"Reported owner earnings ${reported}m. Original valuation unchanged."),
            ("OE BASE — HAP ANALYTICAL OBSERVATION", disc.display_text),
            ("HAP OE-base action", "Reported base retained; HAP has not replaced owner earnings."),
        ]
        if disc.provenance:
            rows.append(("OE-base source", "; ".join(disc.provenance[:3])))
        return rows

    def _write_hap_analysis(
        self,
        path: Path,
        *,
        er_change: str,
        er_original: Any,
        er_hap: Any,
        er_reason: str,
        oe_change: str,
        oe_original: Any,
        oe_hap: Any,
        oe_reason: str,
        eps_change: str,
        eps_original: Any,
        eps_hap: Any,
        eps_reason: str,
        er_analysis: ValuationAssumptionAnalysis | None = None,
        oe_base_disclosure: NormalizedBaseDisclosure | None = None,
    ) -> tuple[list[str], list[str], dict[str, Any]]:
        wb = load_workbook(path, data_only=False)
        written: list[str] = []
        preserved = [
            f"{ER_SHEET}!B5",
            f"{ER_SHEET}!D17",
            f"{ER_SHEET}!E14",
            f"{ER_SHEET}!A11",
            f"{ER_SHEET}!A14",
            f"{ER_SHEET}!C5",
            f"{ER_SHEET}!C17",
            f"{EV_SHEET}!B6",
            f"{EV_SHEET}!C6",
            f"{EV_SHEET}!B20",
            f"{EV_SHEET}!B27",
        ]
        layout = HapAnalysisLayoutService()
        er_parallel: dict[str, Any] = {"coherent": False, "status": "not_required"}
        try:
            if ER_SHEET in wb.sheetnames:
                ws = wb[ER_SHEET]
                orig_b5 = ws["B5"].value
                orig_a11 = ws["A11"].value
                orig_a14 = ws["A14"].value
                orig_c5 = ws["C5"].value
                orig_d17 = [ws[f"D{r}"].value for r in range(17, 27)]
                orig_c17 = [ws[f"C{r}"].value for r in range(17, 27)]
                orig_e14 = ws["E14"].value
                rows: list[tuple[str, Any]] = [
                    ("ORIGINAL WORKBOOK ANALYSIS", ""),
                    ("Original EPS growth assumption (B5)", orig_b5 if orig_b5 is not None else er_original),
                    ("Original sustainable g (A11 = retention × ROE)", orig_a11),
                    ("Original retention (C5)", orig_c5),
                    ("Original ROE (A14)", orig_a14),
                    ("Original Expected Return (E14)", orig_e14 if orig_e14 is not None else "see E14"),
                ]
                clone_ok = False
                if er_change not in {"ACCEPTED", "INSUFFICIENT_EVIDENCE"} and er_hap is not None:
                    er_parallel = self._clone_er_parallel_model(ws, float(er_hap), analysis=er_analysis)
                    clone_ok = bool(er_parallel.get("coherent"))
                    if clone_ok:
                        rows.extend(
                            [
                                ("HAP prospective growth (g slot, not ROE)", float(er_hap)),
                                ("HAP semantic substitution", er_parallel.get("substitution") or ""),
                                (
                                    "HAP Expected Return",
                                    f"={er_parallel['hap_er_cell'].split('!')[-1]}"
                                    if er_parallel.get("hap_er_cell")
                                    else "see HAP parallel model",
                                ),
                                ("HAP rationale", er_reason),
                            ]
                        )
                        written.extend(er_parallel.get("written") or [])
                    else:
                        rows.extend(
                            [
                                ("HAP-adjusted EPS growth", "No coherent parallel Expected Return constructed"),
                                ("HAP-adjusted Expected Return", "INSUFFICIENT_EVIDENCE"),
                                (
                                    "HAP rationale",
                                    er_parallel.get("failure_reason")
                                    or "Cannot construct a coherent HAP Expected Return without misusing ROE as growth.",
                                ),
                            ]
                        )
                else:
                    hap_growth = (
                        "No adjustment recommended"
                        if er_change != "INSUFFICIENT_EVIDENCE"
                        else "No alternative rate selected (insufficient evidence)"
                    )
                    rows.extend(
                        [
                            ("HAP-adjusted EPS growth", hap_growth),
                            ("HAP-adjusted Expected Return", hap_growth),
                            ("HAP rationale", er_reason),
                        ]
                    )
                written.extend(layout.write_block(ws, rows=rows))
                if ws["B5"].value != orig_b5 or [ws[f"D{r}"].value for r in range(17, 27)] != orig_d17:
                    ws["B5"].value = orig_b5
                    for i, val in enumerate(orig_d17):
                        ws[f"D{17 + i}"].value = val
                    for i, val in enumerate(orig_c17):
                        ws[f"C{17 + i}"].value = val
                    ws["E14"].value = orig_e14
                    ws["A11"].value = orig_a11
                    ws["A14"].value = orig_a14
                    ws["C5"].value = orig_c5

            if EV_SHEET in wb.sheetnames:
                ws = wb[EV_SHEET]
                orig_b6, orig_c6 = ws["B6"].value, ws["C6"].value
                orig_b20, orig_b27 = ws["B20"].value, ws["B27"].value
                rows = [
                    ("ORIGINAL WORKBOOK ANALYSIS", ""),
                    ("Original OE total historical change (B6, evidence only)", orig_b6 if orig_b6 is not None else oe_original),
                    ("Original OE annualized forecast driver (C6)", orig_c6),
                    ("Original Enterprise Value / share (B20)", orig_b20),
                    ("Original Margin of Safety (B27)", orig_b27),
                ]
                if oe_change in {"ACCEPTED", "INSUFFICIENT_EVIDENCE"} or oe_hap is None:
                    hap_oe = (
                        "No adjustment recommended"
                        if oe_change != "INSUFFICIENT_EVIDENCE"
                        else "No alternative rate selected (insufficient evidence)"
                    )
                    rows.extend(
                        [
                            ("HAP-adjusted OE growth", hap_oe),
                            ("HAP-adjusted Enterprise Value", hap_oe),
                            ("HAP-adjusted Margin of Safety", hap_oe),
                            ("HAP rationale", oe_reason),
                        ]
                    )
                else:
                    rows.extend(
                        [
                            ("HAP-adjusted OE growth", float(oe_hap)),
                            ("HAP-adjusted Enterprise Value", "Calculated from HAP OE path (original unchanged)"),
                            ("HAP-adjusted Margin of Safety", "Calculated from HAP EV (original unchanged)"),
                            ("HAP rationale", oe_reason),
                        ]
                    )
                rows.extend(self._oe_base_disclosure_rows(oe_base_disclosure))
                written.extend(layout.write_block(ws, rows=rows))
                if oe_change not in {"ACCEPTED", "INSUFFICIENT_EVIDENCE"} and oe_hap is not None:
                    written.extend(self._clone_ev_projections(ws, float(oe_hap)))
                ws["B6"].value = orig_b6
                ws["C6"].value = orig_c6
                ws["B20"].value = orig_b20
                ws["B27"].value = orig_b27

                graham_rows = [
                    ("GRAHAM — ORIGINAL", ""),
                    ("Original relevant growth assumption", eps_original),
                    ("Original Graham Entry Price", ws["B32"].value),
                ]
                if eps_change in {"ACCEPTED", "INSUFFICIENT_EVIDENCE"} or eps_hap is None:
                    hap_g = (
                        "No adjustment recommended"
                        if eps_change != "INSUFFICIENT_EVIDENCE"
                        else "No alternative rate selected (insufficient evidence)"
                    )
                    graham_rows.extend(
                        [
                            ("HAP-adjusted Graham growth", hap_g),
                            ("HAP-adjusted Graham Entry Price", hap_g),
                            ("HAP rationale", eps_reason),
                        ]
                    )
                else:
                    graham_rows.extend(
                        [
                            ("HAP-adjusted Graham growth", float(eps_hap)),
                            (
                                "HAP-adjusted Graham Entry Price",
                                f"=(B51+({float(eps_hap)}*100*B52))*B40",
                            ),
                            ("HAP rationale", eps_reason),
                        ]
                    )
                written.extend(layout.write_block(ws, rows=graham_rows, start_col=10))

            wb.save(path)
        finally:
            wb.close()
        return written, preserved, er_parallel

    @staticmethod
    def _clone_er_parallel_model(
        ws,
        hap_rate: float,
        *,
        analysis: ValuationAssumptionAnalysis | None = None,
    ) -> dict[str, Any]:
        """Build a HAP Expected Return using the workbook's economic roles.

        Growth is never written into an ROE-semantic cell. Originals untouched.
        """
        from openpyxl.cell.cell import MergedCell
        from openpyxl.utils import get_column_letter

        from services.formula_utils import is_formula
        from services.hap_analysis_layout_service import cell_is_occupied_or_formula
        from services.workbook_flag_service import style_hap_analysis_cell

        def fail(reason: str) -> dict[str, Any]:
            return {
                "coherent": False,
                "status": "incoherent",
                "failure_reason": reason,
                "written": [],
                "hap_er_cell": None,
                "substitution": None,
                "hap_mechanics": {},
            }

        d17 = str(ws["D17"].value or "")
        c17 = str(ws["C17"].value or "")
        d17u = d17.upper().replace("$", "").replace(" ", "")
        c17u = c17.upper().replace("$", "").replace(" ", "")
        methodology = None
        if d17.startswith("=") and "C17" in d17u and "A14" in d17u:
            methodology = "bv_x_roe"
        elif d17.startswith("=") and "B5" in d17u and "POWER" in d17u:
            methodology = "eps_growth_power"
        elif c17.startswith("=") and "A11" in c17u:
            methodology = "bv_x_roe"
        if methodology is None:
            return fail("Cannot identify Expected Return path methodology from C17/D17.")

        def _present(addr: str) -> bool:
            v = ws[addr].value
            return v not in (None, "") or is_formula(v)

        if not _present("A2") or not _present("B8") or not _present("E2"):
            return fail("Missing A2 price, B8 book value, or E2 Max PE10 required to reproduce E14.")
        if methodology == "bv_x_roe":
            a14 = ws["A14"].value
            if a14 in (None, ""):
                return fail("ROE (A14) is missing; cannot preserve EPS = BV × ROE.")
            if isinstance(a14, (int, float)) and not isinstance(a14, bool) and a14 <= 0:
                return fail("ROE (A14) is non-positive; EPS = BV × ROE is not a coherent parallel model.")

        def _col_free(c: int) -> bool:
            for row in range(1, 31):
                cell = ws.cell(row, c)
                if isinstance(cell, MergedCell) or cell.value not in (None, ""):
                    return False
            return True

        col = None
        for probe in range(12, 21):
            if _col_free(probe) and _col_free(probe + 1) and _col_free(probe + 2):
                col = probe
                break
        if col is None:
            return fail("No unused adjacent columns for a HAP Expected Return parallel model.")

        label_letter = get_column_letter(col)
        val_letter = get_column_letter(col + 1)
        eps_letter = val_letter
        written: list[str] = []

        def put(row: int, c: int, value: Any) -> str:
            cell = ws.cell(row, c)
            if cell_is_occupied_or_formula(ws, cell.coordinate):
                return ""
            cell.value = value
            style_hap_analysis_cell(cell)
            written.append(f"{ws.title}!{cell.coordinate}")
            return f"{ws.title}!{cell.coordinate}"

        hap_g_addr = f"${val_letter}$5"
        hap_roe_addr = f"${val_letter}$4"
        defect = None
        if analysis is not None:
            defect = (analysis.historical_observations or {}).get("retention_defect_class")
        a11_num = _num(ws["A11"].value)
        mechanism_broken = defect in {"D", "E"} or (a11_num is not None and abs(a11_num) > 1.0)
        put(3, col, "HAP implied retention (b = g / ROE)")
        put(4, col, "HAP ROE (semantic ROE; not a growth rate)")
        put(
            5,
            col,
            "HAP prospective growth (semantic g; replaces unusable A11)"
            if mechanism_broken
            else "HAP prospective growth (semantic g; A11 role)",
        )
        put(6, col, "HAP BV in 10 years")
        put(7, col, "HAP EPS in 10 years")
        put(8, col, "HAP price in 10 years")
        put(9, col, "HAP Expected Return")
        put(10, col, "HAP semantic substitution")

        if methodology == "bv_x_roe":
            if mechanism_broken:
                substitution = (
                    "The original sustainable-growth mechanism (A11 = retention × ROE) is economically "
                    "unusable. HAP replaces A11 with a prospective growth rate in the growth slot only "
                    "for HAP_ANALYSIS. ROE remains A14. Implied HAP retention = g / ROE. "
                    "BV path uses g; EPS path remains BV × ROE; E14 remains (P10/P0)^(1/10)-1. "
                    "A growth rate is not written into an ROE-semantic field. Original formulas are unchanged."
                )
            else:
                substitution = (
                    "HAP substitutes a prospective growth rate for A11 in the growth slot because the "
                    "existing rate is economically unsupported by independent evidence. ROE remains A14. "
                    "Implied HAP retention = g / ROE. BV path uses g; EPS path remains BV × ROE; "
                    "E14 remains (P10/P0)^(1/10)-1. Original formulas are unchanged."
                )
            put(4, col + 1, "=$A$14")
            put(5, col + 1, float(hap_rate))
            put(3, col + 1, f"=IF({hap_roe_addr}=0,\"n/a\",{hap_g_addr}/{hap_roe_addr})")
            put(6, col + 1, f"=$B$8*((1+{hap_g_addr})^10)")
            put(7, col + 1, f"={val_letter}6*{hap_roe_addr}")
            put(8, col + 1, f"={val_letter}7*$E$2")
            hap_er_cell = put(9, col + 1, f"=({val_letter}8/$A$2)^(1/10)-1")
            put(10, col + 1, substitution)
            put(16, col, "HAP BV path")
            put(16, col + 1, "HAP EPS path (BV × ROE)")
            put(16, col + 2, "HAP dividend path")
            for row in range(17, 27):
                orig_c = ws.cell(row, 3).value
                orig_d = ws.cell(row, 4).value
                orig_e = ws.cell(row, 5).value
                if isinstance(orig_c, str) and orig_c.startswith("="):
                    put(row, col, _rewrite_er_formula(orig_c, g_cell=hap_g_addr, roe_cell=hap_roe_addr, bv_col=col, eps_col=col + 1))
                else:
                    put(row, col, f"=$B$8*((1+{hap_g_addr})^B{row})")
                if isinstance(orig_d, str) and orig_d.startswith("="):
                    put(row, col + 1, _rewrite_er_formula(orig_d, g_cell=hap_g_addr, roe_cell=hap_roe_addr, bv_col=col, eps_col=col + 1))
                else:
                    put(row, col + 1, f"={label_letter}{row}*{hap_roe_addr}")
                if isinstance(orig_e, str) and orig_e.startswith("="):
                    put(row, col + 2, _rewrite_er_formula(orig_e, g_cell=hap_g_addr, roe_cell=hap_roe_addr, bv_col=col, eps_col=col + 1))
            hap_mechanics = {
                "methodology": methodology,
                "hap_g_cell": f"{ws.title}!{val_letter}5",
                "hap_roe_cell": f"{ws.title}!{val_letter}4",
                "hap_retention_cell": f"{ws.title}!{val_letter}3",
                "hap_bv_path": f"{ws.title}!{label_letter}17:{label_letter}26",
                "hap_eps_path": f"{ws.title}!{eps_letter}17:{eps_letter}26",
                "hap_expected_return_formula": f"{ws.title}!{val_letter}9",
            }
        else:
            substitution = (
                "Workbook EPS path grows current EPS at B5. HAP writes the prospective rate "
                "into the EPS-growth slot (B5 role), not into ROE. Terminal price = EPS10 × MaxPE10; "
                "Expected Return = (P10/P0)^(1/10)-1."
            )
            put(4, col + 1, "n/a — EPS-growth methodology does not use ROE as the projection driver")
            put(5, col + 1, float(hap_rate))
            put(3, col + 1, "n/a — retention × ROE is not the projection identity")
            put(16, col + 1, "HAP EPS path (EPS × (1+g)^t)")
            for row in range(17, 27):
                orig_d = ws.cell(row, 4).value
                if isinstance(orig_d, str) and orig_d.startswith("="):
                    put(
                        row,
                        col + 1,
                        _rewrite_er_formula(
                            orig_d,
                            g_cell=hap_g_addr,
                            roe_cell=hap_roe_addr,
                            bv_col=col,
                            eps_col=col + 1,
                            map_b5_to_g=True,
                        ),
                    )
                else:
                    put(row, col + 1, f"='Final Metrics'!$L$29*POWER(1+{hap_g_addr},B{row})")
            put(7, col + 1, f"={eps_letter}26")
            put(8, col + 1, f"={val_letter}7*$E$2")
            hap_er_cell = put(9, col + 1, f"=({val_letter}8/$A$2)^(1/10)-1")
            put(10, col + 1, substitution)
            hap_mechanics = {
                "methodology": methodology,
                "hap_g_cell": f"{ws.title}!{val_letter}5",
                "hap_eps_path": f"{ws.title}!{eps_letter}17:{eps_letter}26",
                "hap_expected_return_formula": f"{ws.title}!{val_letter}9",
            }

        if not hap_er_cell:
            return fail("HAP Expected Return cell could not be written (occupied).")
        return {
            "coherent": True,
            "status": "formulas_written",
            "failure_reason": None,
            "written": written,
            "hap_er_cell": hap_er_cell,
            "substitution": substitution,
            "hap_mechanics": hap_mechanics,
            "hap_g_cell": f"{ws.title}!{val_letter}5",
            "hap_roe_cell": f"{ws.title}!{val_letter}4" if methodology == "bv_x_roe" else None,
        }

    @staticmethod
    def _clone_ev_projections(ws, hap_rate: float) -> list[str]:
        """Reproduce OE extrapolation with the HAP rate in unused rows; originals untouched."""
        from openpyxl.utils import get_column_letter

        from services.formula_utils import parse_cell_refs
        from services.hap_analysis_layout_service import cell_is_occupied_or_formula, discover_unused_column
        from services.workbook_flag_service import style_hap_analysis_cell

        written: list[str] = []
        col = discover_unused_column(ws, start_col=16, end_col=24, scan_rows=20)
        letter = get_column_letter(col)
        rate = ws.cell(5, col)
        if cell_is_occupied_or_formula(ws, rate.coordinate):
            return written
        rate.value = float(hap_rate)
        style_hap_analysis_cell(rate)
        written.append(f"{ws.title}!{rate.coordinate}")
        label = ws.cell(4, col)
        if not cell_is_occupied_or_formula(ws, label.coordinate):
            label.value = "HAP OE annualized growth"
            style_hap_analysis_cell(label)
            written.append(f"{ws.title}!{label.coordinate}")

        def rewrite(formula: str, *, row_map: dict[int, int]) -> str:
            pieces: list[str] = []
            last = 0
            for ref in parse_cell_refs(formula):
                pieces.append(formula[last : ref["start"]])
                row = row_map.get(ref["row"], ref["row"])
                if ref["sheet"] is None and ref["col"] == 3 and ref["row"] == 6:
                    abs_c = "$" if ref["col_abs"] else ""
                    abs_r = "$" if ref["row_abs"] else ""
                    pieces.append(f"{abs_c}{letter}{abs_r}5")
                else:
                    abs_c = "$" if ref["col_abs"] else ""
                    abs_r = "$" if ref["row_abs"] else ""
                    sheet = ""
                    if ref["sheet"]:
                        name = ref["sheet"]
                        sheet = f"'{name}'!" if (" " in name or not name.replace("_", "").isalnum()) else f"{name}!"
                    pieces.append(f"{sheet}{abs_c}{get_column_letter(ref['col'])}{abs_r}{row}")
                last = ref["end"]
            pieces.append(formula[last:])
            return "".join(pieces)

        for src_col in range(2, 22):
            orig9 = ws.cell(9, src_col).value
            dest9 = ws.cell(54, src_col)
            if isinstance(orig9, str) and orig9.startswith("=") and not cell_is_occupied_or_formula(ws, dest9.coordinate):
                dest9.value = rewrite(orig9, row_map={})
                style_hap_analysis_cell(dest9)
                written.append(f"{ws.title}!{dest9.coordinate}")
            orig10 = ws.cell(10, src_col).value
            dest10 = ws.cell(55, src_col)
            if isinstance(orig10, str) and orig10.startswith("=") and not cell_is_occupied_or_formula(ws, dest10.coordinate):
                dest10.value = rewrite(orig10, row_map={9: 54})
                style_hap_analysis_cell(dest10)
                written.append(f"{ws.title}!{dest10.coordinate}")

        extras = (
            (56, 1, "HAP SUM Owners Earnings"),
            (56, 2, "=SUM(B55:U55)"),
            (57, 1, "HAP Company Value"),
            (57, 2, "=B56+B17"),
            (58, 1, "HAP Company Value/Share"),
            (58, 2, "=B57/'Last Quarter BS Standardized'!C122"),
            (59, 1, "HAP Margin of Safety"),
            (59, 2, "=(B57-B25)/B57"),
        )
        for row, c, val in extras:
            cell = ws.cell(row, c)
            if cell_is_occupied_or_formula(ws, cell.coordinate):
                continue
            cell.value = val
            style_hap_analysis_cell(cell)
            written.append(f"{ws.title}!{cell.coordinate}")
        return written
