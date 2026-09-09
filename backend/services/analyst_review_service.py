"""Analyst review of validated statement history (no workbook writes)."""

from __future__ import annotations

from typing import Any

from models.analyst_review import (
    AnalystFinding,
    AnalystReviewReport,
    ExplanationStatus,
    FindingSeverity,
)
from models.statement_validation import (
    StatementValidationDecision,
    StatementValidationReport,
)
from services.sec_service import SecService

# One-time / unusual SEC concepts to surface when present for a FY.
_UNUSUAL_TAGS: list[tuple[str, str, str]] = [
    # metric_key, tag, observation template
    (
        "Restructuring charges",
        "RestructuringCharges",
        "Restructuring charges reported in SEC companyfacts",
    ),
    (
        "Goodwill impairment",
        "GoodwillImpairmentLoss",
        "Goodwill impairment loss reported in SEC companyfacts",
    ),
    (
        "Asset impairment",
        "ImpairmentOfLongLivedAssetsHeldForUse",
        "Long-lived asset impairment reported in SEC companyfacts",
    ),
    (
        "Litigation settlement",
        "LossContingencyAccrual",
        "Loss contingency / litigation accrual reported",
    ),
    (
        "Gain on sale",
        "GainLossOnSaleOfBusiness",
        "Gain/loss on sale of business reported",
    ),
    (
        "Discontinued operations",
        "IncomeLossFromDiscontinuedOperationsNetOfTax",
        "Discontinued operations result reported",
    ),
    (
        "Acquisition costs",
        "BusinessCombinationAcquisitionRelatedCosts",
        "Acquisition-related costs reported",
    ),
]


def _fy_year(token: str) -> int | None:
    digits = "".join(ch for ch in str(token) if ch.isdigit())
    if len(digits) >= 4:
        return int(digits[-4:])
    return None


class AnalystReviewService:
    """
    Surface economically meaningful movements and one-time items.

    Validation confirms trustworthiness; this layer explains what an analyst
    would investigate next. Never modifies the workbook.
    """

    def __init__(self, sec_service: SecService | None = None) -> None:
        self.sec = sec_service or SecService()

    def review(
        self,
        *,
        analysis_id: str,
        ticker: str,
        validation: StatementValidationReport,
        company_facts: dict[str, Any],
    ) -> AnalystReviewReport:
        findings: list[AnalystFinding] = []

        # Index validated workbook series for trend work.
        series = self._series_from_validation(validation)

        findings.extend(self._revenue_growth_findings(series))
        findings.extend(self._margin_findings(series))
        findings.extend(self._balance_sheet_findings(series))
        findings.extend(self._cash_flow_findings(series))
        findings.extend(self._one_time_findings(company_facts, series))
        findings.extend(self._discrepancy_findings(validation))

        findings = self._rank_and_cap(findings, limit=40)

        material = sum(1 for f in findings if f.severity == FindingSeverity.MATERIAL)
        watch = sum(1 for f in findings if f.severity == FindingSeverity.WATCH)
        info = sum(1 for f in findings if f.severity == FindingSeverity.INFO)
        summary = (
            f"Analyst review: {material} MATERIAL, {watch} WATCH, {info} INFO "
            f"({len(findings)} ranked findings; validation discrepancies kept separate)."
        )
        return AnalystReviewReport(
            analysis_id=analysis_id,
            ticker=ticker,
            findings=findings,
            material_count=material,
            watch_count=watch,
            info_count=info,
            summary=summary,
        )

    def _series_from_validation(
        self, validation: StatementValidationReport
    ) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for e in validation.entries:
            if e.workbook_value is None:
                continue
            if e.decision not in {
                StatementValidationDecision.VALIDATED,
                StatementValidationDecision.REVIEW_REQUIRED,
                StatementValidationDecision.DISCREPANCY,
            }:
                # Still allow trends from workbook even if SOURCE_MISSING for SEC
                if e.decision == StatementValidationDecision.SOURCE_MISSING:
                    key = f"{e.statement}|{e.metric}"
                    out.setdefault(key, {})[e.fiscal_period] = float(e.workbook_value)
                continue
            key = f"{e.statement}|{e.metric}"
            out.setdefault(key, {})[e.fiscal_period] = float(e.workbook_value)
        return out

    def _ordered_years(self, by_period: dict[str, float]) -> list[tuple[str, float]]:
        items: list[tuple[int, str, float]] = []
        for period, value in by_period.items():
            year = _fy_year(period)
            if year is None:
                continue
            items.append((year, period, value))
        items.sort(key=lambda x: x[0])
        return [(p, v) for _, p, v in items]

    def _revenue_growth_findings(
        self, series: dict[str, dict[str, float]]
    ) -> list[AnalystFinding]:
        rev = series.get("income_statement|Revenue") or {}
        ordered = self._ordered_years(rev)
        findings: list[AnalystFinding] = []
        for i in range(1, len(ordered)):
            prev_p, prev_v = ordered[i - 1]
            cur_p, cur_v = ordered[i]
            if prev_v == 0:
                continue
            yoy = (cur_v - prev_v) / abs(prev_v)
            if abs(yoy) < 0.15:
                continue
            severity = FindingSeverity.MATERIAL if abs(yoy) >= 0.25 else FindingSeverity.WATCH
            direction = "decline" if yoy < 0 else "growth"
            findings.append(
                AnalystFinding(
                    statement="income_statement",
                    metric="Revenue",
                    period=cur_p,
                    severity=severity,
                    observation=(
                        f"Revenue {direction} of {yoy:.1%} YoY "
                        f"({prev_p}: {prev_v:,.0f} → {cur_p}: {cur_v:,.0f} USD millions)"
                    ),
                    quantitative_evidence={
                        "prior_period": prev_p,
                        "prior_value": prev_v,
                        "current_value": cur_v,
                        "yoy_change": round(yoy, 4),
                    },
                    sec_explanation=(
                        "If both periods VALIDATED against SEC, this is a business-performance "
                        "finding — not a fiscal-period or data-identity error."
                    ),
                    explanation_status=ExplanationStatus.LIKELY_EXPLANATION,
                    source_references=["workbook Income - GAAP", "SEC companyfacts revenue"],
                    analyst_relevance="Investigate drivers in MD&A / segment notes for this FY.",
                    is_data_discrepancy=False,
                )
            )
        return findings

    def _margin_findings(
        self, series: dict[str, dict[str, float]]
    ) -> list[AnalystFinding]:
        rev = series.get("income_statement|Revenue") or {}
        gp = series.get("income_statement|Gross Profit") or {}
        oi = series.get("income_statement|Operating Income") or {}
        findings: list[AnalystFinding] = []
        years = sorted(
            {_fy_year(p) for p in rev if _fy_year(p)},
        )
        margins: list[tuple[str, float, float]] = []
        for y in years:
            period = f"FY{y}"
            if period not in rev or period not in gp or rev[period] == 0:
                continue
            gm = gp[period] / rev[period]
            om = (oi[period] / rev[period]) if period in oi else None
            margins.append((period, gm, om if om is not None else float("nan")))

        for i in range(1, len(margins)):
            prev_p, prev_gm, prev_om = margins[i - 1]
            cur_p, cur_gm, cur_om = margins[i]
            gm_delta = cur_gm - prev_gm
            if abs(gm_delta) >= 0.02:  # 200 bps
                sev = FindingSeverity.MATERIAL if abs(gm_delta) >= 0.05 else FindingSeverity.WATCH
                findings.append(
                    AnalystFinding(
                        statement="income_statement",
                        metric="Gross Margin",
                        period=cur_p,
                        severity=sev,
                        observation=(
                            f"Gross margin moved {gm_delta*100:.0f} bps "
                            f"({prev_p}: {prev_gm:.1%} → {cur_p}: {cur_gm:.1%})"
                        ),
                        quantitative_evidence={
                            "prior_gross_margin": round(prev_gm, 4),
                            "current_gross_margin": round(cur_gm, 4),
                            "delta": round(gm_delta, 4),
                        },
                        explanation_status=ExplanationStatus.UNEXPLAINED_REVIEW_REQUIRED,
                        source_references=["workbook Income - GAAP"],
                        analyst_relevance="Review cost mix, product mix, and MD&A margin commentary.",
                    )
                )
            if prev_om == prev_om and cur_om == cur_om:  # not NaN
                om_delta = cur_om - prev_om
                if abs(om_delta) >= 0.03:
                    sev = (
                        FindingSeverity.MATERIAL if abs(om_delta) >= 0.06 else FindingSeverity.WATCH
                    )
                    findings.append(
                        AnalystFinding(
                            statement="income_statement",
                            metric="Operating Margin",
                            period=cur_p,
                            severity=sev,
                            observation=(
                                f"Operating margin moved {om_delta*100:.0f} bps "
                                f"({prev_p}: {prev_om:.1%} → {cur_p}: {cur_om:.1%})"
                            ),
                            quantitative_evidence={
                                "prior_operating_margin": round(prev_om, 4),
                                "current_operating_margin": round(cur_om, 4),
                                "delta": round(om_delta, 4),
                            },
                            explanation_status=ExplanationStatus.UNEXPLAINED_REVIEW_REQUIRED,
                            source_references=["workbook Income - GAAP"],
                            analyst_relevance="Check opex, R&D, SG&A, and one-time operating items.",
                        )
                    )
        return findings

    def _balance_sheet_findings(
        self, series: dict[str, dict[str, float]]
    ) -> list[AnalystFinding]:
        findings: list[AnalystFinding] = []
        for metric_key, label in (
            ("balance_sheet|Cash", "Cash"),
            ("balance_sheet|Total Assets", "Total Assets"),
            ("balance_sheet|Total Liabilities", "Total Liabilities"),
            ("balance_sheet|Total Equity", "Total Equity"),
        ):
            ordered = self._ordered_years(series.get(metric_key) or {})
            for i in range(1, len(ordered)):
                prev_p, prev_v = ordered[i - 1]
                cur_p, cur_v = ordered[i]
                if prev_v == 0:
                    continue
                yoy = (cur_v - prev_v) / abs(prev_v)
                abs_chg = abs(cur_v - prev_v)
                if abs(yoy) < 0.20 and abs_chg < 5000:
                    continue
                severity = (
                    FindingSeverity.MATERIAL
                    if abs(yoy) >= 0.35 or abs_chg >= 20000
                    else FindingSeverity.WATCH
                )
                findings.append(
                    AnalystFinding(
                        statement="balance_sheet",
                        metric=label,
                        period=cur_p,
                        severity=severity,
                        observation=(
                            f"{label} changed {yoy:.1%} YoY "
                            f"({prev_v:,.0f} → {cur_v:,.0f} USD millions)"
                        ),
                        quantitative_evidence={
                            "prior_value": prev_v,
                            "current_value": cur_v,
                            "yoy_change": round(yoy, 4),
                            "absolute_change": round(cur_v - prev_v, 2),
                        },
                        explanation_status=ExplanationStatus.UNEXPLAINED_REVIEW_REQUIRED,
                        source_references=["workbook Balance Sheet - Standardized"],
                        analyst_relevance=(
                            "Review debt activity, acquisitions, buybacks, and working capital notes."
                        ),
                    )
                )
        return findings

    def _cash_flow_findings(
        self, series: dict[str, dict[str, float]]
    ) -> list[AnalystFinding]:
        findings: list[AnalystFinding] = []
        cfo = self._ordered_years(series.get("cash_flow|Operating Cash Flow") or {})
        ni = {
            p: v
            for p, v in (series.get("income_statement|Net Income") or {}).items()
        }
        for i in range(1, len(cfo)):
            prev_p, prev_v = cfo[i - 1]
            cur_p, cur_v = cfo[i]
            if prev_v == 0:
                continue
            yoy = (cur_v - prev_v) / abs(prev_v)
            if abs(yoy) >= 0.25:
                findings.append(
                    AnalystFinding(
                        statement="cash_flow",
                        metric="Operating Cash Flow",
                        period=cur_p,
                        severity=(
                            FindingSeverity.MATERIAL if abs(yoy) >= 0.40 else FindingSeverity.WATCH
                        ),
                        observation=f"CFO changed {yoy:.1%} YoY ({prev_v:,.0f} → {cur_v:,.0f})",
                        quantitative_evidence={
                            "prior_value": prev_v,
                            "current_value": cur_v,
                            "yoy_change": round(yoy, 4),
                        },
                        explanation_status=ExplanationStatus.UNEXPLAINED_REVIEW_REQUIRED,
                        source_references=["workbook Cash Flow - Standardized"],
                        analyst_relevance="Inspect WC swings, deferred taxes, and non-cash items.",
                    )
                )
            if cur_p in ni and ni[cur_p] != 0:
                conv = cur_v / abs(ni[cur_p])
                if conv < 0.5 or conv > 2.5:
                    findings.append(
                        AnalystFinding(
                            statement="cash_flow",
                            metric="Cash conversion",
                            period=cur_p,
                            severity=FindingSeverity.WATCH,
                            observation=(
                                f"CFO/|Net Income| = {conv:.2f} "
                                f"(CFO {cur_v:,.0f}, NI {ni[cur_p]:,.0f})"
                            ),
                            quantitative_evidence={
                                "cfo": cur_v,
                                "net_income": ni[cur_p],
                                "cfo_to_ni": round(conv, 3),
                            },
                            explanation_status=ExplanationStatus.UNEXPLAINED_REVIEW_REQUIRED,
                            source_references=["workbook Income - GAAP", "Cash Flow - Standardized"],
                            analyst_relevance="Earnings vs cash divergence warrants WC/quality review.",
                        )
                    )

        for metric_key, label in (
            ("cash_flow|Share Repurchases", "Share Repurchases"),
            ("cash_flow|Dividends", "Dividends"),
            ("cash_flow|Capital Expenditures", "Capital Expenditures"),
        ):
            ordered = self._ordered_years(series.get(metric_key) or {})
            for i in range(1, len(ordered)):
                prev_p, prev_v = ordered[i - 1]
                cur_p, cur_v = ordered[i]
                if abs(prev_v) < 1:
                    continue
                yoy = (cur_v - prev_v) / abs(prev_v)
                if abs(yoy) < 0.40 and abs(cur_v - prev_v) < 2000:
                    continue
                findings.append(
                    AnalystFinding(
                        statement="cash_flow",
                        metric=label,
                        period=cur_p,
                        severity=FindingSeverity.WATCH,
                        observation=f"{label} changed {yoy:.1%} YoY ({prev_v:,.0f} → {cur_v:,.0f})",
                        quantitative_evidence={
                            "prior_value": prev_v,
                            "current_value": cur_v,
                            "yoy_change": round(yoy, 4),
                        },
                        explanation_status=ExplanationStatus.LIKELY_EXPLANATION,
                        source_references=["workbook Cash Flow - Standardized"],
                        analyst_relevance="Capital allocation / investment intensity change.",
                    )
                )
        return findings

    def _one_time_findings(
        self,
        company_facts: dict[str, Any],
        series: dict[str, dict[str, float]],
    ) -> list[AnalystFinding]:
        findings: list[AnalystFinding] = []
        # Years present in revenue series
        years = sorted(
            {
                y
                for key, by_p in series.items()
                if key.startswith("income_statement|")
                for p in by_p
                if (y := _fy_year(p)) is not None
            }
        )
        if not years:
            years = list(range(2016, 2026))

        for metric, tag, obs in _UNUSUAL_TAGS:
            for year in years:
                fact = self.sec.find_fact(
                    company_facts,
                    tag,
                    f"FY{year}",
                    xbrl_tag_hint=tag,
                )
                if fact is None or fact.value is None:
                    continue
                value = float(fact.value)
                if abs(value) < 50_000_000:  # ignore trivial
                    continue
                millions = value / 1_000_000.0
                findings.append(
                    AnalystFinding(
                        statement="income_statement",
                        metric=metric,
                        period=f"FY{year}",
                        severity=FindingSeverity.MATERIAL,
                        observation=f"{obs}: {millions:,.0f} USD millions (SEC)",
                        quantitative_evidence={
                            "sec_value_usd": value,
                            "sec_value_millions": millions,
                            "xbrl_tag": tag,
                        },
                        sec_explanation=(
                            f"SEC {fact.form} fact {tag} for FY{year} "
                            f"(accession {fact.accession_number}). "
                            "Treat as filing-supported unusual item; validate presentation in notes."
                        ),
                        explanation_status=ExplanationStatus.EXPLAINED_BY_FILING,
                        source_references=[
                            f"SEC {fact.form}",
                            tag,
                            str(fact.accession_number or ""),
                        ],
                        analyst_relevance="One-time / unusual item — exclude or adjust in quality analysis.",
                        is_data_discrepancy=False,
                    )
                )
        return findings

    def _discrepancy_findings(
        self, validation: StatementValidationReport
    ) -> list[AnalystFinding]:
        findings: list[AnalystFinding] = []
        for e in validation.entries:
            if e.decision != StatementValidationDecision.DISCREPANCY:
                continue
            findings.append(
                AnalystFinding(
                    statement=e.statement,
                    metric=e.metric,
                    period=e.fiscal_period,
                    severity=FindingSeverity.MATERIAL,
                    observation=(
                        f"Data discrepancy: workbook {e.workbook_value} vs SEC {e.sec_value} "
                        f"at {e.workbook_cell}"
                    ),
                    quantitative_evidence={
                        "workbook_value": e.workbook_value,
                        "sec_value": e.sec_value,
                        "absolute_difference": e.absolute_difference,
                        "percentage_difference": e.percentage_difference,
                    },
                    sec_explanation="SEC is authoritative for resolution; value not auto-rewritten.",
                    explanation_status=ExplanationStatus.UNEXPLAINED_REVIEW_REQUIRED,
                    source_references=[
                        e.workbook_cell,
                        e.sec_concept or "",
                        e.accession_number or "",
                    ],
                    analyst_relevance="Resolve discrepancy before relying on this input for analysis.",
                    is_data_discrepancy=True,
                    status="open",
                )
            )
        return findings

    def _rank_and_cap(
        self, findings: list[AnalystFinding], *, limit: int
    ) -> list[AnalystFinding]:
        rank = {FindingSeverity.MATERIAL: 0, FindingSeverity.WATCH: 1, FindingSeverity.INFO: 2}

        def sort_key(f: AnalystFinding) -> tuple:
            abs_yoy = abs(float((f.quantitative_evidence or {}).get("yoy_change") or 0))
            abs_chg = abs(float((f.quantitative_evidence or {}).get("absolute_change") or 0))
            return (rank[f.severity], 0 if f.is_data_discrepancy else 1, -abs_yoy, -abs_chg)

        findings.sort(key=sort_key)
        return findings[:limit]
