"""Read-only Expected Return / EPS growth review for Industrial Template."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.expected_return_validation import (
    AdjustmentNecessity,
    EpsHistoryPoint,
    EpsOutlierJudgment,
    ExpectedReturnAnalystItem,
    ExpectedReturnAnalystReview,
    ExpectedReturnDecision,
    ExpectedReturnPeriodAssumptions,
    ExpectedReturnValidationReport,
)
from workbook_mapping.explicit_mappings import ANNUAL_PERIOD_COLS, ANNUAL_PERIOD_FY_TOKENS

ER_SHEET = "Expected Returns & Buybacks"
INCOME_SHEET = "Income - GAAP"
FINAL_METRICS_SHEET = "Final Metrics"
INPUTS_SHEET = "Inputs"
BS_SHEET = "Balance Sheet - Standardized"

EPS_ROW = 71
_YOY_OUTLIER = 0.50  # |YoY| > 50% → candidate for judgment
_EPS_ABS_TOL = 0.05
_GROWTH_ABS_TOL = 0.015  # 150 bps
_ER_ABS_TOL = 0.005


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # Excel error strings sometimes appear as floats; reject NaN
        if value != value:  # NaN
            return None
        return float(value)
    text = str(value).strip()
    if text.startswith("#"):
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _cagr(start: float | None, end: float | None, years: int) -> float | None:
    if start is None or end is None or years <= 0:
        return None
    if start <= 0 or end <= 0:
        return None  # negative/near-zero denominator — not defined for house CAGR
    return (end / start) ** (1.0 / years) - 1.0


def _yoy(prev: float | None, cur: float | None) -> float | None:
    if prev is None or cur is None:
        return None
    if abs(prev) < 1e-9:
        return None  # near-zero denominator
    return (cur / prev) - 1.0


def _period_from_bs(bs, col: int, fallback: str) -> str:
    if bs is None:
        return fallback
    v = bs.cell(8, col).value
    if v is not None and hasattr(v, "year"):
        return f"FY{v.year}"
    return fallback


def _split_multiple(workbook: float, sec: float) -> float | None:
    if workbook == 0 or sec == 0:
        return None
    ratio = abs(sec / workbook)
    for split in (2.0, 3.0, 4.0, 5.0, 7.0, 10.0):
        if abs(ratio - split) <= 0.08:
            return split
    return None


def interpret_attractiveness(expected_return: float | None, *, treasury: float | None = None) -> str:
    if expected_return is None:
        return "indeterminate"
    hurdle = (treasury or 0.04) + 0.03
    if expected_return >= hurdle + 0.04:
        return "attractive"
    if expected_return >= hurdle:
        return "acceptable"
    if expected_return >= hurdle - 0.02:
        return "marginal"
    return "unattractive"


def reconstruct_expected_annual_return(
    *,
    terminal_price: float,
    current_price: float,
    years: int = 10,
) -> float | None:
    if current_price <= 0 or terminal_price <= 0 or years <= 0:
        return None
    return (terminal_price / current_price) ** (1.0 / years) - 1.0


class ExpectedReturnValidationService:
    """Inspect Expected Returns & Buybacks; validate EPS growth and ER math."""

    def validate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        company_facts: dict[str, Any] | None = None,
    ) -> ExpectedReturnValidationReport:
        path = Path(workbook_path)
        wb_v = load_workbook(path, data_only=True)
        wb_f = load_workbook(path, data_only=False)

        methodology = self._methodology(wb_f)
        eps_history = self._eps_history(wb_v, company_facts)
        outliers = self._outlier_judgments(eps_history, company_facts)
        growth = self._growth_assessment(wb_v, eps_history)
        er_block = self._expected_return_block(wb_v, wb_f, growth)

        overall = self._overall(eps_history, growth, er_block["decision"], outliers)
        attractiveness = er_block.get("attractiveness")
        summary = (
            f"Expected Return review {ticker}: EPS points={len(eps_history)}, "
            f"growth={growth.growth_decision.value}, "
            f"ER={er_block['decision'].value}, attractiveness={attractiveness}. "
            f"{er_block['explanation']}"
        )

        report = ExpectedReturnValidationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=str(path),
            methodology=methodology,
            eps_history=eps_history,
            outliers=outliers,
            growth=growth,
            current_price=er_block.get("current_price"),
            max_pe10=er_block.get("max_pe10"),
            workbook_expected_return=er_block.get("workbook_er"),
            independent_expected_return=er_block.get("independent_er"),
            expected_return_difference=er_block.get("difference"),
            expected_return_decision=er_block["decision"],
            expected_return_explanation=er_block["explanation"],
            attractiveness=attractiveness,
            overall_decision=overall,
            summary=summary,
            evidence=er_block.get("evidence") or {},
        )
        wb_v.close()
        wb_f.close()
        return report

    def build_analyst_review(
        self, report: ExpectedReturnValidationReport
    ) -> ExpectedReturnAnalystReview:
        items: list[ExpectedReturnAnalystItem] = []

        split_pts = [
            p for p in report.eps_history if p.decision == ExpectedReturnDecision.NOT_COMPARABLE
        ]
        if split_pts:
            items.append(
                ExpectedReturnAnalystItem(
                    topic="split_adjusted_eps_comparability",
                    status=ExpectedReturnDecision.VALIDATED,
                    observation=(
                        f"{len(split_pts)} early periods show as-reported SEC EPS vs "
                        "split-adjusted workbook EPS — not treated as accounting errors."
                    ),
                    quantitative_evidence={
                        "periods": [p.period for p in split_pts],
                        "samples": [
                            {"period": p.period, "wb": p.workbook_eps, "sec": p.sec_eps}
                            for p in split_pts[:3]
                        ],
                    },
                    interpretation="Use workbook split-adjusted series for growth; do not force as-reported SEC.",
                    recommendation="preserve_split_adjusted_history",
                )
            )

        for o in report.outliers:
            items.append(
                ExpectedReturnAnalystItem(
                    topic="eps_outlier_judgment",
                    period=o.period,
                    status=o.decision,
                    observation=o.reason,
                    quantitative_evidence={
                        "reported_eps": o.reported_eps,
                        "yoy_growth": o.yoy_growth,
                        "necessity": o.necessity.value,
                        "sec_evidence": o.sec_evidence,
                        **o.quantitative_impact,
                    },
                    interpretation=(
                        "Do not auto-adjust historical EPS without filing support."
                        if o.necessity == AdjustmentNecessity.NOT_JUSTIFIED
                        else "Analyst may consider normalization if evidence supports."
                    ),
                )
            )

        items.append(
            ExpectedReturnAnalystItem(
                topic="growth_assumption",
                status=report.growth.growth_decision,
                observation=report.growth.growth_explanation,
                quantitative_evidence={
                    "workbook": report.growth.workbook_growth_assumption,
                    "independent_cagr": report.growth.independent_eps_cagr,
                    "recent_5y": report.growth.recent_5y_cagr,
                    "range": [
                        report.growth.independent_growth_low,
                        report.growth.independent_growth_high,
                    ],
                },
                interpretation=report.growth.growth_explanation,
            )
        )

        items.append(
            ExpectedReturnAnalystItem(
                topic="expected_return_output",
                status=report.expected_return_decision,
                observation=report.expected_return_explanation,
                quantitative_evidence={
                    "workbook": report.workbook_expected_return,
                    "independent": report.independent_expected_return,
                    "current_price": report.current_price,
                    "max_pe10": report.max_pe10,
                },
                interpretation=(
                    f"Attractiveness={report.attractiveness} — input to later valuation, "
                    "not a final investment recommendation."
                ),
            )
        )

        return ExpectedReturnAnalystReview(
            analysis_id=report.analysis_id,
            ticker=report.ticker,
            items=items,
            attractiveness=report.attractiveness,
            summary=(
                f"{len(items)} expected-return analyst items; "
                f"overall={report.overall_decision.value}; "
                f"attractiveness={report.attractiveness}."
            ),
        )

    # ------------------------------------------------------------------

    def _methodology(self, wb_f) -> dict[str, Any]:
        er = wb_f[ER_SHEET] if ER_SHEET in wb_f.sheetnames else None
        fm = wb_f[FINAL_METRICS_SHEET] if FINAL_METRICS_SHEET in wb_f.sheetnames else None
        return {
            "sheet": ER_SHEET,
            "eps_source": f"{INCOME_SHEET} row {EPS_ROW} Diluted EPS, GAAP (via Inputs!row41 → Final Metrics row29)",
            "historical_growth_cell": "Expected Returns!B5 = Final Metrics!L31",
            "historical_growth_formula": "EPS 10Y CAGR = (EPS_end/EPS_start)^(1/9)-1 (ending column)",
            "expected_annual_return_cell": "Expected Returns!E14",
            "expected_annual_return_formula": "(Price_in_10y / Current_Price)^(1/10)-1",
            "price_in_10y": "C14 = EPS_in_10y * MaxPE10 (E2)",
            "eps_in_10y": "B14 = BV_in_10y * Average_ROE (A14)",
            "bv_growth": "A11 = RetainedEarningsAvg% * AverageROE (C5*A14)",
            "current_price": "A2 = Final Metrics!B51 = Inputs!B63",
            "bloomberg_alternate": "Inputs!B69 / Final Metrics!B57 Expected Return @ Current Price",
            "analyst_adjustment_cells": "Inputs EPS growth sinks C59:L60 (often Bloomberg); ER projection uses ROE/BV path",
            "sample_formulas": {
                "B5": er["B5"].value if er else None,
                "E14": er["E14"].value if er else None,
                "L31": fm["L31"].value if fm else None,
            },
            "no_workbook_writes": True,
        }

    def _eps_history(
        self, wb_v, company_facts: dict[str, Any] | None
    ) -> list[EpsHistoryPoint]:
        if INCOME_SHEET not in wb_v.sheetnames:
            return []
        income = wb_v[INCOME_SHEET]
        bs = wb_v[BS_SHEET] if BS_SHEET in wb_v.sheetnames else None
        sec_map = self._sec_eps_map(company_facts) if company_facts else {}

        points: list[EpsHistoryPoint] = []
        prev_wb: float | None = None
        for idx, col_letter in enumerate(ANNUAL_PERIOD_COLS):
            col = 3 + idx
            period = _period_from_bs(bs, col, ANNUAL_PERIOD_FY_TOKENS[idx])
            wb_eps = _num(income.cell(EPS_ROW, col).value)
            sec_eps = sec_map.get(period)
            yoy = _yoy(prev_wb, wb_eps)
            decision, reason, split_ok = self._compare_eps(wb_eps, sec_eps)
            points.append(
                EpsHistoryPoint(
                    period=period,
                    workbook_eps=wb_eps,
                    sec_eps=sec_eps,
                    workbook_cell=f"{INCOME_SHEET}!{col_letter}{EPS_ROW}",
                    decision=decision,
                    reason=reason,
                    yoy_growth=yoy,
                    split_adjusted_comparable=split_ok,
                )
            )
            if wb_eps is not None:
                prev_wb = wb_eps
        return points

    def _sec_eps_map(self, company_facts: dict[str, Any]) -> dict[str, float]:
        from services.sec_service import SecService

        sec = SecService()
        out: dict[str, float] = {}
        for fy in ANNUAL_PERIOD_FY_TOKENS:
            year = int(fy.replace("FY", ""))
            fact = sec.find_fact(
                company_facts,
                "earnings per share",
                f"FY{year}",
                xbrl_tag_hint="EarningsPerShareDiluted",
            )
            if fact is not None and fact.value is not None:
                out[f"FY{year}"] = float(fact.value)
        return out

    def _compare_eps(
        self, workbook: float | None, sec: float | None
    ) -> tuple[ExpectedReturnDecision, str, bool]:
        if workbook is None:
            return ExpectedReturnDecision.SOURCE_MISSING, "Workbook EPS blank", True
        if sec is None:
            return (
                ExpectedReturnDecision.VALIDATED,
                "Workbook EPS present; SEC fact unavailable for period",
                True,
            )
        if abs(workbook - sec) <= _EPS_ABS_TOL:
            return ExpectedReturnDecision.VALIDATED, "Workbook EPS matches SEC diluted EPS", True
        split = _split_multiple(workbook, sec)
        if split is not None:
            return (
                ExpectedReturnDecision.NOT_COMPARABLE,
                f"SEC as-reported vs workbook split-adjusted (≈{split:.0f}:1) — not an accounting error",
                False,
            )
        # Also accept workbook ≈ sec/split
        return (
            ExpectedReturnDecision.DISCREPANCY,
            f"EPS mismatch workbook={workbook} sec={sec}",
            True,
        )

    def _outlier_judgments(
        self,
        history: list[EpsHistoryPoint],
        company_facts: dict[str, Any] | None,
    ) -> list[EpsOutlierJudgment]:
        judgments: list[EpsOutlierJudgment] = []
        for pt in history:
            if pt.yoy_growth is None:
                continue
            if abs(pt.yoy_growth) < _YOY_OUTLIER:
                continue
            # Statistical outlier — require filing evidence to adjust
            evidence = self._one_time_item_hint(pt.period, company_facts)
            if evidence:
                judgments.append(
                    EpsOutlierJudgment(
                        period=pt.period,
                        reported_eps=pt.workbook_eps,
                        proposed_normalized_eps=None,
                        yoy_growth=pt.yoy_growth,
                        quantitative_impact={"abs_yoy": abs(pt.yoy_growth)},
                        reason=f"Large YoY EPS move ({pt.yoy_growth:.0%}) with possible one-time context.",
                        sec_evidence=evidence,
                        confidence=0.55,
                        necessity=AdjustmentNecessity.OPTIONAL,
                        decision=ExpectedReturnDecision.REVIEW_REQUIRED,
                    )
                )
            else:
                judgments.append(
                    EpsOutlierJudgment(
                        period=pt.period,
                        reported_eps=pt.workbook_eps,
                        proposed_normalized_eps=None,
                        yoy_growth=pt.yoy_growth,
                        quantitative_impact={"abs_yoy": abs(pt.yoy_growth)},
                        reason=(
                            f"Statistical YoY outlier ({pt.yoy_growth:.0%}) without concrete "
                            "one-time filing evidence — do not adjust EPS automatically."
                        ),
                        sec_evidence=None,
                        confidence=0.7,
                        necessity=AdjustmentNecessity.NOT_JUSTIFIED,
                        decision=ExpectedReturnDecision.WATCH,
                    )
                )
        return judgments

    def _one_time_item_hint(
        self, period: str, company_facts: dict[str, Any] | None
    ) -> str | None:
        """Conservative: only flag known restructuring/impairment tags if present for FY."""
        if not company_facts:
            return None
        from services.sec_service import SecService

        sec = SecService()
        year = period.replace("FY", "")
        tags = [
            "RestructuringCharges",
            "GoodwillImpairmentLoss",
            "ImpairmentOfLongLivedAssetsHeldForUse",
            "LitigationSettlementExpense",
            "DisposalGroupIncludingDiscontinuedOperationOperatingIncomeLoss",
        ]
        hits = []
        for tag in tags:
            fact = sec.find_fact(company_facts, tag, f"FY{year}", xbrl_tag_hint=tag)
            if fact is not None and fact.value is not None and abs(float(fact.value)) > 0:
                hits.append(f"{tag}={fact.value}")
        if not hits:
            return None
        return "; ".join(hits[:3])

    def _growth_assessment(
        self, wb_v, history: list[EpsHistoryPoint]
    ) -> ExpectedReturnPeriodAssumptions:
        series = [p.workbook_eps for p in history if p.workbook_eps is not None]
        independent = None
        recent5 = None
        if len(series) >= 2:
            independent = _cagr(series[0], series[-1], len(series) - 1)
        if len(series) >= 6:
            recent5 = _cagr(series[-6], series[-1], 5)

        wb_growth = None
        if ER_SHEET in wb_v.sheetnames:
            wb_growth = _num(wb_v[ER_SHEET]["B5"].value)
        if wb_growth is None and FINAL_METRICS_SHEET in wb_v.sheetnames:
            wb_growth = _num(wb_v[FINAL_METRICS_SHEET]["L31"].value)

        # Independent reviewed range: blend recent vs full-history; cap exuberance
        low = high = None
        if independent is not None and recent5 is not None:
            low = min(independent, recent5) * 0.75
            high = max(independent, recent5)
            # Mature-business sanity: if decade CAGR > 20%, flag upper as watch
        elif independent is not None:
            low = independent * 0.7
            high = independent

        decision = ExpectedReturnDecision.REVIEW_REQUIRED
        explanation = "Insufficient EPS history for growth assessment."
        if wb_growth is not None and independent is not None:
            if abs(wb_growth - independent) <= _GROWTH_ABS_TOL:
                decision = ExpectedReturnDecision.VALIDATED
                explanation = (
                    f"Workbook EPS growth assumption {wb_growth:.1%} reconciles to "
                    f"independent diluted-EPS CAGR {independent:.1%}."
                )
            else:
                decision = ExpectedReturnDecision.DISCREPANCY
                explanation = (
                    f"Workbook growth {wb_growth:.1%} differs from independent CAGR "
                    f"{independent:.1%} beyond tolerance."
                )
            # Maturity watch: high historical CAGR should not be blindly extrapolated
            if independent is not None and independent > 0.18:
                if decision == ExpectedReturnDecision.VALIDATED:
                    decision = ExpectedReturnDecision.WATCH
                explanation += (
                    " Historical CAGR is elevated for a large-cap compounder — "
                    "do not extrapolate the peak decade rate as the forward assumption without review."
                )
            if recent5 is not None and independent is not None and abs(recent5 - independent) > 0.05:
                explanation += (
                    f" Recent 5y CAGR {recent5:.1%} differs from full-window CAGR; "
                    "consider regime change."
                )

        return ExpectedReturnPeriodAssumptions(
            workbook_eps_cagr=wb_growth,
            independent_eps_cagr=independent,
            recent_5y_cagr=recent5,
            workbook_growth_assumption=wb_growth,
            independent_growth_low=low,
            independent_growth_high=high,
            growth_decision=decision,
            growth_explanation=explanation,
        )

    def _expected_return_block(
        self, wb_v, wb_f, growth: ExpectedReturnPeriodAssumptions
    ) -> dict[str, Any]:
        er_v = wb_v[ER_SHEET] if ER_SHEET in wb_v.sheetnames else None
        fm_v = wb_v[FINAL_METRICS_SHEET] if FINAL_METRICS_SHEET in wb_v.sheetnames else None
        inputs = wb_v[INPUTS_SHEET] if INPUTS_SHEET in wb_v.sheetnames else None

        current_price = _num(er_v["A2"].value) if er_v else None
        if current_price is None and fm_v is not None:
            current_price = _num(fm_v["B51"].value)
        if current_price is None and inputs is not None:
            current_price = _num(inputs["B63"].value)

        max_pe = _num(er_v["E2"].value) if er_v else None
        terminal_price = _num(er_v["C14"].value) if er_v else None
        workbook_er = _num(er_v["E14"].value) if er_v else None
        # Bloomberg alternate sink
        bloomberg_er = None
        if inputs is not None:
            bloomberg_er = _num(inputs["B69"].value)
        if bloomberg_er is None and fm_v is not None:
            bloomberg_er = _num(fm_v["B57"].value)

        independent_er = None
        if terminal_price is not None and current_price is not None and current_price > 0:
            independent_er = reconstruct_expected_annual_return(
                terminal_price=terminal_price,
                current_price=current_price,
                years=10,
            )
        # If terminal price zero because MaxPE blank, try reconstruct from components
        if independent_er is None and er_v is not None:
            eps_10 = _num(er_v["B14"].value)
            if eps_10 is not None and max_pe is not None and current_price and current_price > 0:
                tp = eps_10 * max_pe
                independent_er = reconstruct_expected_annual_return(
                    terminal_price=tp, current_price=current_price, years=10
                )
                terminal_price = tp

        difference = None
        if workbook_er is not None and independent_er is not None:
            difference = workbook_er - independent_er

        treasury = None
        if er_v is not None:
            treasury = _num(er_v["B2"].value)

        if current_price is None or current_price <= 0:
            decision = ExpectedReturnDecision.SOURCE_MISSING
            explanation = (
                "Current price (Expected Returns!A2 / Inputs!B63) missing — "
                "house expected-return formula divides by price and yields #DIV/0!."
            )
            attractiveness = "indeterminate"
        elif workbook_er is None and independent_er is None:
            decision = ExpectedReturnDecision.SOURCE_MISSING
            explanation = "Expected return outputs unavailable (price or terminal value inputs incomplete)."
            attractiveness = "indeterminate"
        elif workbook_er is not None and independent_er is not None:
            if abs(workbook_er - independent_er) <= _ER_ABS_TOL:
                decision = ExpectedReturnDecision.VALIDATED
                explanation = (
                    f"House expected annual return {workbook_er:.1%} reconciles to "
                    f"independent reconstruction {independent_er:.1%}."
                )
            else:
                decision = ExpectedReturnDecision.DISCREPANCY
                explanation = (
                    f"Expected return mismatch workbook={workbook_er:.1%} "
                    f"independent={independent_er:.1%}."
                )
            attractiveness = interpret_attractiveness(workbook_er, treasury=treasury)
        elif independent_er is not None:
            decision = ExpectedReturnDecision.WATCH
            explanation = (
                f"Independent ER {independent_er:.1%} reconstructed; workbook cell blank/error."
            )
            attractiveness = interpret_attractiveness(independent_er, treasury=treasury)
        else:
            decision = ExpectedReturnDecision.REVIEW_REQUIRED
            explanation = "Unable to validate expected return with available inputs."
            attractiveness = "indeterminate"

        if bloomberg_er is not None and workbook_er is None:
            explanation += f" Bloomberg Inputs!B69 ER={bloomberg_er:.1%} present as alternate sink."

        return {
            "current_price": current_price,
            "max_pe10": max_pe,
            "workbook_er": workbook_er,
            "independent_er": independent_er,
            "difference": difference,
            "decision": decision,
            "explanation": explanation,
            "attractiveness": attractiveness,
            "evidence": {
                "terminal_price": terminal_price,
                "bloomberg_er": bloomberg_er,
                "treasury_yield": treasury,
                "growth_assumption": growth.workbook_growth_assumption,
                "er_e14_formula": wb_f[ER_SHEET]["E14"].value
                if ER_SHEET in wb_f.sheetnames
                else None,
            },
        }

    def _overall(
        self,
        history: list[EpsHistoryPoint],
        growth: ExpectedReturnPeriodAssumptions,
        er_decision: ExpectedReturnDecision,
        outliers: list[EpsOutlierJudgment],
    ) -> ExpectedReturnDecision:
        statuses = [p.decision for p in history if p.decision != ExpectedReturnDecision.NOT_COMPARABLE]
        statuses.append(growth.growth_decision)
        statuses.append(er_decision)
        statuses.extend(o.decision for o in outliers)
        if any(s == ExpectedReturnDecision.DISCREPANCY for s in statuses):
            return ExpectedReturnDecision.DISCREPANCY
        if any(s == ExpectedReturnDecision.SOURCE_MISSING for s in statuses):
            # Missing price is common pre-completion — still elevate
            if er_decision == ExpectedReturnDecision.SOURCE_MISSING:
                return ExpectedReturnDecision.REVIEW_REQUIRED
            return ExpectedReturnDecision.SOURCE_MISSING
        if any(s == ExpectedReturnDecision.REVIEW_REQUIRED for s in statuses):
            return ExpectedReturnDecision.REVIEW_REQUIRED
        if any(s == ExpectedReturnDecision.WATCH for s in statuses):
            return ExpectedReturnDecision.WATCH
        return ExpectedReturnDecision.VALIDATED
