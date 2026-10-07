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
from services.tab_notes import add_notes
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
        if er_a.decision == "ADJUST":
            # The expected return is checked and, when unrealistic, switched to the EPS-growth model by the valuation corrections step.
            # No parallel alternative is built beside the original any more.
            er_a.decision = "KEEP_EXISTING"
            er_a.selected_prospective_rate = None
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
    def _live_rows(rows: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
        """Only the formula rows (the HAP alternative calculated beside the model). Prose goes to the single Notes block."""
        return [(label, value) for label, value in rows
                if isinstance(value, str) and value.startswith("=") and str(label).upper().startswith("HAP")]

    @staticmethod
    def _valuation_note(what: str, change: str, hap_value: Any, *, kind: str) -> list[str]:
        """What HAP did with one valuation assumption, in plain language."""
        from services.tab_notes import note

        source = "the company's financial history in this workbook"
        if change == "ACCEPTED":
            return [note(f"The {what} was reviewed and left as it is", "it looks consistent with the company's history", source)]
        if change == "INSUFFICIENT_EVIDENCE":
            return [note(f"No alternative {what} was proposed", "the evidence was not strong enough to replace the workbook's assumption", source)]
        rate = f" ({float(hap_value) * 100:.1f}% a year)" if isinstance(hap_value, (int, float)) else ""
        return [note(f"An alternative {what}{rate} was calculated beside the original, which was left unchanged",
                     "the original assumption looks distorted or hard to sustain", source)]

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
                rows.extend(
                    [
                        ("HAP-adjusted EPS growth", "Handled by the expected return check (see the notes)"),
                        ("HAP-adjusted Expected Return", "Handled by the expected return check (see the notes)"),
                        ("HAP rationale", er_reason),
                    ]
                )
                written.extend(layout.place_analysis_notes(ws, self._live_rows(rows)))
                review = getattr(self, "input_review", None)
                er_review_notes = review.notes("expected_return") if review else []
                add_notes(
                    ws,
                    er_review_notes or self._valuation_note("book value growth used for the expected return", "ACCEPTED", None, kind="er"),
                    replace_containing=("book value growth used for the expected return", "inputs behind this valuation", "return on equity and the book value growth", "No model value was changed",
                                        "expected return and flagged", "typical return on equity"),
                )
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
                written.extend(layout.place_analysis_notes(ws, self._live_rows(rows)))
                review = getattr(self, "input_review", None)
                oe_review_notes = review.notes("owner_earnings") if review else []
                ev_notes = (
                    [] if oe_review_notes and oe_change in {"ACCEPTED", "INSUFFICIENT_EVIDENCE"}
                    else self._valuation_note("owner's earnings growth rate", oe_change, oe_hap, kind="oe")
                ) + oe_review_notes
                if oe_base_disclosure is not None and oe_base_disclosure.decision == DISCLOSE_DISTORTED_BASE and oe_base_disclosure.display_text:
                    ev_notes.append(" ".join(oe_base_disclosure.display_text.split()))
                if oe_change not in {"ACCEPTED", "INSUFFICIENT_EVIDENCE"} and oe_hap is not None:
                    written.extend(self._clone_ev_projections(ws, float(oe_hap)))
                ws["B6"].value = orig_b6
                ws["C6"].value = orig_c6
                ws["B20"].value = orig_b20
                ws["B27"].value = orig_b27

                graham_rows = [
                    ("GRAHAM — BASE MODEL", "rows 38:48 preserved"),
                    ("Original relevant growth assumption", eps_original),
                    ("Original Graham entry target (B48)", ws["B48"].value),
                ]
                if eps_change not in {"ACCEPTED", "INSUFFICIENT_EVIDENCE"} and eps_hap is not None:
                    written.extend(self._write_graham_alternative(ws, float(eps_hap)))
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
                                "HAP alternative entry target",
                                "Enterprise Value!F48 uses the B48 identity on the HAP growth rate",
                            ),
                            ("HAP rationale", eps_reason),
                        ]
                    )
                written.extend(layout.place_analysis_notes(ws, self._live_rows(graham_rows), live_start_col=10))
                ev_notes += self._valuation_note("growth rate used in the Graham valuation", eps_change, eps_hap, kind="graham")
                add_notes(
                    ws,
                    ev_notes,
                    replace_containing=("owner's earnings growth rate", "growth rate used in the Graham valuation", "inputs behind this valuation",
                                        "No model value was changed", "owner's earnings growth rate used", "typical basis"),
                )

            wb.save(path)
        finally:
            wb.close()
        return written, preserved, er_parallel

    @staticmethod
    def _write_graham_alternative(ws, hap_rate: float) -> list[str]:
        """Side-by-side Graham alternative in E/F rows 38:48. Entry target uses the B48 identity."""
        from services.hap_analysis_layout_service import cell_is_occupied_or_formula
        from services.workbook_flag_service import style_hap_analysis_cell

        pairs: list[tuple[str, Any, str | None]] = [
            ("E38", "HAP Alternative / Conservative Scenario", None),
            ("E39", "HAP EPS growth", None),
            ("F39", float(hap_rate), "0.0%"),
            ("E42", "HAP Graham intrinsic value", None),
            ("F42", "=(B51+(F39*100*B52))*B40", None),
            ("E43", "HAP growth used in the year-7 multiple", None),
            ("F43", "=MIN(F39,0.07)", "0.0%"),
            ("E44", "HAP EPS in year 7", None),
            ("F44", '=IF(1+F39<0,"invalid growth",B40*(1+F39)^7)', None),
            ("E45", "HAP Graham multiple in year 7", None),
            ("F45", "=(F43*100)*B52+B51", None),
            ("E46", "HAP Graham value in year 7", None),
            ("F46", '=IF(OR(NOT(ISNUMBER(F44)),NOT(ISNUMBER(F45))),"invalid",F44*F45)', None),
            ("E47", "HAP expected annualized return", None),
            (
                "F47",
                '=IF(OR(B39="",B39=0,NOT(ISNUMBER(F46))),"base model limitation",(F46/B39)^(1/7)-1)',
                "0.00%",
            ),
            ("E48", "HAP entry target price", None),
            (
                "F48",
                '=IF(OR(1+B53<=0,NOT(ISNUMBER(F46))),"invalid target",F46/(1+B53)^7)',
                '"$"#,##0.00',
            ),
        ]
        written: list[str] = []
        for addr, value, fmt in pairs:
            if cell_is_occupied_or_formula(ws, addr):
                continue
            cell = ws[addr]
            cell.value = value
            if fmt:
                cell.number_format = fmt
            style_hap_analysis_cell(cell)
            written.append(f"{ws.title}!{addr}")
        return written

    @staticmethod
    def _clone_ev_projections(ws, hap_rate: float) -> list[str]:
        """Reproduce OE extrapolation with the HAP rate in unused rows; originals untouched."""
        from openpyxl.utils import get_column_letter

        from services.formula_utils import parse_cell_refs
        from services.hap_analysis_layout_service import cell_is_occupied_or_formula, discover_unused_column
        from services.workbook_flag_service import style_hap_analysis_cell

        written: list[str] = []
        # A53 is the Graham target-return parameter on the industrial template.
        for label_row in (54, 52):
            title = ws.cell(label_row, 1)
            if title.value in (None, ""):
                title.value = "HAP Alternative / Conservative Scenario"
                style_hap_analysis_cell(title)
                written.append(f"{ws.title}!A{label_row}")
                break
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
