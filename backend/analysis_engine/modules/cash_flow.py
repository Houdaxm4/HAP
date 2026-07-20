"""Cash Flow analysis module — FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM.

Consumes only ``CompanyFinancialModel``. Produces a 0–100 Cash Flow Score
with confidence, HAP metrics, findings (CF001–CF006), risks, opportunities,
evidence, workbook metric comparisons, and analyst adjustment proposals.
"""

from __future__ import annotations

from typing import Any

from analysis_engine.base import AnalysisModule
from analysis_engine.metric_comparison import attach_metric_comparisons
from analysis_engine.schemas import (
    AnalysisModuleResult,
    AnalystAdjustmentProposal,
    Evidence,
    Finding,
    MetricResult,
    OpportunityItem,
    RiskItem,
)
from analysis_engine.utils import mean, paired_periods, ratio_series, safe_div
from canonical_model import CompanyFinancialModel, FinancialPoint, FinancialSeries
from rule_library.cash_flow import CashFlowRuleInputs, evaluate_cash_flow_rules
from scoring_engine.cash_flow import CashFlowScoreInputs, score_cash_flow

TREND_WINDOW = 5

_CASH_FLOW_COMPARABLE_CODES = frozenset(
    {
        "FCF_MARGIN",
        "CASH_CONVERSION",
        "OWNER_EARNINGS",
        "OWNER_EARNINGS_MARGIN",
        "FCF_STABILITY",
        "LATEST_FCF",
        "LATEST_OCF",
        "CAPEX_RATIO",
    }
)

_RISK_BY_RULE: dict[str, str] = {
    "CF003": "POOR_CASH_CONVERSION",
    "CF004": "PERSISTENT_CASH_BURN",
    "CF006": "HIGH_CAPEX_DEPENDENCY",
}

_OPP_BY_RULE: dict[str, str] = {
    "CF001": "CONSISTENT_CASH_GENERATION",
    "CF002": "EXCEPTIONAL_CASH_CONVERSION",
    "CF005": "STRONG_OWNER_EARNINGS",
}


class CashFlowModule(AnalysisModule):
    """Evaluate cash generation quality and emit the Cash Flow Score."""

    module_id = "cash_flow"
    module_version = "1.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        cfs = model.cash_flow_statement
        income = model.income_statement
        ocf_series = cfs.operating_cash_flow
        fcf_series = cfs.free_cash_flow
        capex_series = cfs.capital_expenditures
        revenue_series = income.revenue
        ni_series = income.net_income

        if ocf_series.is_empty and fcf_series.is_empty:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={"operating_cash_flow": False, "free_cash_flow": False},
                error="Insufficient cash flow inputs (need operating or free cash flow series).",
            )

        metadata = dict(model.metadata or {})
        fcf_series = _resolve_fcf_series(ocf_series, capex_series, fcf_series)
        owner_earnings_series = _build_owner_earnings_series(
            model, ocf_series, capex_series, metadata
        )
        fcf_margin_series = ratio_series(
            name="FCF Margin",
            numerator=fcf_series,
            denominator=revenue_series,
            currency="ratio",
        )
        owner_earnings_margin_series = ratio_series(
            name="Owner Earnings Margin",
            numerator=owner_earnings_series,
            denominator=revenue_series,
            currency="ratio",
        )
        cash_conversion_series = ratio_series(
            name="Cash Conversion",
            numerator=ocf_series,
            denominator=ni_series,
            currency="ratio",
        )
        capex_ratio_series = ratio_series(
            name="CapEx Ratio",
            numerator=_abs_series(capex_series),
            denominator=revenue_series,
            currency="ratio",
        )

        period = (
            (fcf_series.latest() or ocf_series.latest() or owner_earnings_series.latest()).period
            if (fcf_series.latest() or ocf_series.latest() or owner_earnings_series.latest())
            else None
        )

        latest_fcf = fcf_series.latest().value if fcf_series.latest() else None
        latest_ocf = ocf_series.latest().value if ocf_series.latest() else None
        fcf_margin = fcf_margin_series.latest().value if fcf_margin_series.latest() else None
        cash_conversion = (
            cash_conversion_series.latest().value if cash_conversion_series.latest() else None
        )
        owner_earnings = (
            owner_earnings_series.latest().value if owner_earnings_series.latest() else None
        )
        owner_earnings_margin = (
            owner_earnings_margin_series.latest().value
            if owner_earnings_margin_series.latest()
            else None
        )
        capex_ratio = capex_ratio_series.latest().value if capex_ratio_series.latest() else None
        fcf_stability = (
            fcf_series.stability(TREND_WINDOW) if len(fcf_series) >= 2 else None
        )
        fcf_cagr = fcf_series.cagr(TREND_WINDOW) if len(fcf_series) >= 2 else None
        capex_cagr = (
            _abs_series(capex_series).cagr(TREND_WINDOW)
            if len(capex_series) >= 2
            else None
        )
        revenue_cagr = (
            revenue_series.cagr(TREND_WINDOW) if len(revenue_series) >= 2 else None
        )
        owner_earnings_cagr = (
            owner_earnings_series.cagr(TREND_WINDOW)
            if len(owner_earnings_series) >= 2
            else None
        )

        fcf_by_period = {
            point.period: point.value
            for point in fcf_series.window_points(TREND_WINDOW)
            if point.period
        }
        owner_earnings_by_period = {
            point.period: point.value
            for point in owner_earnings_series.window_points(TREND_WINDOW)
            if point.period
        }

        metrics: list[MetricResult] = []
        evidence_bag: list[Evidence] = []
        evidence_by_metric: dict[str, list[Evidence]] = {}

        metric_defs: list[tuple[str, str, float | None, str]] = [
            ("Operating Cash Flow", "LATEST_OCF", latest_ocf, model.reporting_currency),
            ("Free Cash Flow", "LATEST_FCF", latest_fcf, model.reporting_currency),
            ("FCF Margin", "FCF_MARGIN", fcf_margin, "ratio"),
            ("Cash Conversion", "CASH_CONVERSION", cash_conversion, "ratio"),
            ("Owner Earnings", "OWNER_EARNINGS", owner_earnings, model.reporting_currency),
            ("Owner Earnings Margin", "OWNER_EARNINGS_MARGIN", owner_earnings_margin, "ratio"),
            ("CapEx Ratio", "CAPEX_RATIO", capex_ratio, "ratio"),
            ("FCF CAGR", "FCF_CAGR", fcf_cagr, "ratio"),
            ("Owner Earnings CAGR", "OWNER_EARNINGS_CAGR", owner_earnings_cagr, "ratio"),
            ("FCF Stability", "FCF_STABILITY", fcf_stability, "score"),
            ("OCF History Length", "OCF_HISTORY_YEARS", float(len(ocf_series.points)), "count"),
            ("FCF History Length", "FCF_HISTORY_YEARS", float(len(fcf_series.points)), "count"),
        ]

        confidence_penalty = 0.0
        if cfs.free_cash_flow.is_empty and not fcf_series.is_empty:
            confidence_penalty += 0.06
        if not metadata.get("maintenance_capex_by_period") and not metadata.get(
            "maintenance_capex_series"
        ):
            confidence_penalty += 0.05
        if cash_conversion is None:
            confidence_penalty += 0.08
        if len(fcf_series) < 3:
            confidence_penalty += 0.06

        for name, code, value, unit in metric_defs:
            if value is None:
                continue
            ev = [
                Evidence(
                    kind="derived_metric",
                    label=name,
                    metric=code,
                    period=period,
                    value=value,
                    unit=unit,
                    confidence=0.85,
                    details={"window": TREND_WINDOW},
                )
            ]
            evidence_by_metric[code] = ev
            evidence_bag.extend(ev)
            metrics.append(
                MetricResult(
                    name=name,
                    code=code,
                    value=value,
                    unit=unit,
                    period=period,
                    confidence=0.85,
                    evidence=ev,
                )
            )

        score_evidence = {
            "FREE_CASH_FLOW": evidence_by_metric.get("FCF_MARGIN", []),
            "CASH_CONVERSION": evidence_by_metric.get("CASH_CONVERSION", []),
            "OWNER_EARNINGS": evidence_by_metric.get("OWNER_EARNINGS_MARGIN", []),
            "FCF_STABILITY": evidence_by_metric.get("FCF_STABILITY", []),
        }
        score_result = score_cash_flow(
            CashFlowScoreInputs(
                fcf_margin=fcf_margin,
                cash_conversion=cash_conversion,
                owner_earnings_margin=owner_earnings_margin,
                fcf_stability=fcf_stability,
                latest_fcf=latest_fcf,
                period=period,
                evidence=score_evidence,
                input_confidence={
                    "FREE_CASH_FLOW": 0.9,
                    "CASH_CONVERSION": 0.85 if cash_conversion is not None else 0.5,
                    "OWNER_EARNINGS": 0.8,
                    "FCF_STABILITY": 0.8,
                },
                confidence_penalty=confidence_penalty,
            )
        )

        rule_hits = evaluate_cash_flow_rules(
            CashFlowRuleInputs(
                cash_conversion=cash_conversion,
                fcf_by_period=fcf_by_period,
                owner_earnings_by_period=owner_earnings_by_period,
                capex_cagr=capex_cagr,
                revenue_cagr=revenue_cagr,
                latest_fcf=latest_fcf,
                period=period,
                periods=fcf_series.periods()[-TREND_WINDOW:],
                evidence_by_metric=evidence_by_metric,
            )
        )
        findings = [hit.to_finding() for hit in rule_hits]
        for finding in findings:
            evidence_bag.extend(finding.evidence)

        risks, opportunities = self._risks_and_opportunities(findings)
        adjustments = self._adjustment_proposals(
            findings,
            maintenance_capex_available=bool(
                metadata.get("maintenance_capex_by_period")
                or metadata.get("maintenance_capex_series")
            ),
            fcf_history_years=len(fcf_series.points),
        )

        if score_result.score is None and not metrics:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                error="Could not compute cash flow metrics or score.",
            )

        coverage = {
            "operating_cash_flow": not ocf_series.is_empty,
            "free_cash_flow": not fcf_series.is_empty,
            "fcf_derived": cfs.free_cash_flow.is_empty and not fcf_series.is_empty,
            "maintenance_capex_overlay": bool(
                metadata.get("maintenance_capex_by_period")
                or metadata.get("maintenance_capex_series")
            ),
            "fcf_history_years": len(fcf_series.points),
            "ocf_history_years": len(ocf_series.points),
            "effective_weights": score_result.effective_weights,
            "periods_used": fcf_series.periods()[-TREND_WINDOW:],
        }
        comparable_metrics = [
            metric for metric in metrics if metric.code in _CASH_FLOW_COMPARABLE_CODES
        ]
        coverage = attach_metric_comparisons(
            coverage,
            self.build_metric_comparisons(model, comparable_metrics, period=period),
        )

        return AnalysisModuleResult(
            module_name=self.module_id,
            module_version=self.module_version,
            status="ok",
            score=score_result.score,
            confidence=score_result.confidence,
            metrics=metrics,
            findings=findings,
            risks=risks,
            opportunities=opportunities,
            evidence=_unique_evidence(evidence_bag),
            analyst_adjustments=adjustments,
            component_scores=score_result.components,
            coverage=coverage,
        )

    def _risks_and_opportunities(
        self,
        findings: list[Finding],
    ) -> tuple[list[RiskItem], list[OpportunityItem]]:
        risks: list[RiskItem] = []
        opportunities: list[OpportunityItem] = []
        for finding in findings:
            rule_id = finding.rule_id or ""
            if finding.severity in {"warning", "critical", "high", "medium"} and finding.direction == "negative":
                risks.append(
                    RiskItem(
                        risk_id=f"risk:{finding.finding_id}",
                        code=_RISK_BY_RULE.get(rule_id, finding.code),
                        severity=finding.severity,
                        summary=finding.summary,
                        related_finding_ids=[finding.finding_id],
                        evidence=finding.evidence,
                        confidence=finding.confidence,
                    )
                )
            if finding.severity == "positive" and finding.direction == "positive":
                opportunities.append(
                    OpportunityItem(
                        opportunity_id=f"opp:{finding.finding_id}",
                        code=_OPP_BY_RULE.get(rule_id, finding.code),
                        summary=finding.summary,
                        related_finding_ids=[finding.finding_id],
                        evidence=finding.evidence,
                        confidence=finding.confidence,
                    )
                )
        return risks, opportunities

    def _adjustment_proposals(
        self,
        findings: list[Finding],
        *,
        maintenance_capex_available: bool,
        fcf_history_years: int,
    ) -> list[AnalystAdjustmentProposal]:
        adjustments: list[AnalystAdjustmentProposal] = []
        finding_ids = {finding.rule_id: finding.finding_id for finding in findings}

        def _add(
            rule_id: str,
            action: str,
            rationale: str,
            target: str,
            priority: str = "medium",
        ) -> None:
            if rule_id not in finding_ids:
                return
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id=f"cash_flow:adj:{action}:{rule_id.lower()}",
                    action=action,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale_code=rationale,
                    target=target,
                    related_finding_ids=[finding_ids[rule_id]],
                    confidence=0.75,
                )
            )

        _add("CF003", "review_assumption", "WEAK_CASH_CONVERSION", "cash_flow_statement.operating_cash_flow")
        _add("CF003", "remove_one_time", "WEAK_CASH_CONVERSION", "income_statement.net_income")
        _add("CF004", "flag_for_committee", "PERSISTENT_CASH_BURN", "cash_flow_statement.free_cash_flow", "high")
        _add("CF004", "review_assumption", "PERSISTENT_CASH_BURN", "cash_flow_statement.free_cash_flow", "high")
        _add("CF006", "review_assumption", "HIGH_CAPEX_DEPENDENCY", "cash_flow_statement.capital_expenditures")
        _add("CF006", "adjust_forecast", "HIGH_CAPEX_DEPENDENCY", "cash_flow_statement.capital_expenditures")

        if not maintenance_capex_available:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="cash_flow:adj:maintenance-capex-overlay",
                    action="review_assumption",
                    priority="medium",
                    rationale_code="OWNER_EARNINGS_MAINTENANCE_CAPEX",
                    target="metadata.maintenance_capex_by_period",
                    confidence=0.7,
                )
            )

        if fcf_history_years < 5 or "CF004" in finding_ids:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="cash_flow:adj:request-more-history",
                    action="request_more_data",
                    priority="high" if "CF004" in finding_ids else "medium",
                    rationale_code="INSUFFICIENT_CASH_FLOW_HISTORY",
                    target="cash_flow_statement.free_cash_flow",
                    related_finding_ids=[finding_ids["CF004"]] if "CF004" in finding_ids else [],
                    confidence=0.85,
                )
            )

        return adjustments


def _resolve_fcf_series(
    ocf: FinancialSeries,
    capex: FinancialSeries,
    reported_fcf: FinancialSeries,
) -> FinancialSeries:
    """Use reported FCF when present; otherwise derive from OCF and CapEx."""
    if not reported_fcf.is_empty:
        return reported_fcf
    derived = FinancialSeries(name="Free Cash Flow", currency=ocf.currency or reported_fcf.currency)
    for period in paired_periods(ocf, capex):
        ocf_point = ocf.point_for(period)
        capex_point = capex.point_for(period)
        if ocf_point is None or capex_point is None:
            continue
        capex_outflow = abs(capex_point.value)
        derived.upsert(
            FinancialPoint(
                period=period,
                value=ocf_point.value - capex_outflow,
                currency=ocf_point.currency,
                source="derived",
                confidence=mean(
                    [c for c in (ocf_point.confidence, capex_point.confidence) if c is not None]
                ),
                audited=bool(ocf_point.audited and capex_point.audited),
            )
        )
    return derived


def _build_owner_earnings_series(
    model: CompanyFinancialModel,
    ocf: FinancialSeries,
    capex: FinancialSeries,
    metadata: dict[str, Any],
) -> FinancialSeries:
    """Owner earnings = OCF minus maintenance CapEx (overlay or total CapEx proxy)."""
    maintenance = _series_from_metadata(
        metadata.get("maintenance_capex_by_period")
        or metadata.get("maintenance_capex_series"),
        name="Maintenance CapEx",
        currency=model.reporting_currency,
    )
    series = FinancialSeries(name="Owner Earnings", currency=model.reporting_currency)
    for period in paired_periods(ocf, capex):
        ocf_point = ocf.point_for(period)
        capex_point = capex.point_for(period)
        if ocf_point is None:
            continue
        maint_point = maintenance.point_for(period) if not maintenance.is_empty else None
        maint_value = (
            abs(maint_point.value)
            if maint_point is not None
            else abs(capex_point.value)
            if capex_point is not None
            else 0.0
        )
        series.upsert(
            FinancialPoint(
                period=period,
                value=ocf_point.value - maint_value,
                currency=ocf_point.currency,
                source="derived",
                confidence=ocf_point.confidence,
                audited=ocf_point.audited,
            )
        )
    return series


def _abs_series(series: FinancialSeries) -> FinancialSeries:
    converted = FinancialSeries(name=f"|{series.name}|", currency=series.currency)
    for point in series:
        converted.upsert(
            FinancialPoint(
                period=point.period,
                value=abs(point.value),
                currency=point.currency,
                source=point.source or "derived",
                confidence=point.confidence,
                audited=point.audited,
            )
        )
    return converted


def _series_from_metadata(
    raw: Any,
    *,
    name: str,
    currency: str,
) -> FinancialSeries:
    series = FinancialSeries(name=name, currency=currency)
    if isinstance(raw, dict):
        for period, value in raw.items():
            try:
                series.upsert(
                    FinancialPoint(
                        period=str(period),
                        value=abs(float(value)),
                        currency=currency,
                        source="metadata",
                        confidence=0.8,
                    )
                )
            except (TypeError, ValueError):
                continue
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            period = item.get("period")
            value = item.get("value")
            if period is None or value is None:
                continue
            try:
                series.upsert(
                    FinancialPoint(
                        period=str(period),
                        value=abs(float(value)),
                        currency=currency,
                        source="metadata",
                        confidence=float(item.get("confidence") or 0.8),
                    )
                )
            except (TypeError, ValueError):
                continue
    return series


def _unique_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str | None, str | None, str | None, float | None]] = set()
    unique: list[Evidence] = []
    for item in items:
        key = (item.label, item.metric or item.concept, item.period, item.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
