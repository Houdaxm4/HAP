"""Expected Return analysis module — HAP methodology + SCORING_SYSTEM.md.

Estimates forward-looking shareholder return from today's market price,
HAP valuation outputs, growth, yields, and valuation reversion.
Consumes only ``CompanyFinancialModel``. When run inside AnalysisEngine,
reuses the shared valuation compute result.
"""

from __future__ import annotations

from typing import Any

from analysis_engine.base import AnalysisModule
from analysis_engine.expected_return_engine import compute_expected_return
from analysis_engine.metric_comparison import (
    ModuleMetricComparisons,
    attach_metric_comparisons,
    compare_workbook_to_hap,
)
from analysis_engine.schemas import (
    AnalysisModuleResult,
    AnalystAdjustmentProposal,
    Evidence,
    Finding,
    MetricResult,
    OpportunityItem,
    RiskItem,
    ToleranceMode,
)
from analysis_engine.valuation_engine import ValuationComputeResult
from canonical_model import CompanyFinancialModel
from rule_library.expected_return import ExpectedReturnRuleInputs, evaluate_expected_return_rules
from scoring_engine.expected_return import (
    EXPECTED_RETURN_CONFIDENCE_CAP,
    ExpectedReturnScoreInputs,
    score_expected_return,
)

TREND_WINDOW = 5

_ER_COMPARABLE_CODES = frozenset({"EXPECTED_IRR", "EXPECTED_CAGR"})

_WORKBOOK_CODE_MAP = {
    "EXPECTED_IRR": "EXPECTED_IRR",
    "EXPECTED_CAGR": "EXPECTED_CAGR",
}

_COMPARISON_TOLERANCE: dict[str, tuple[float, ToleranceMode]] = {
    "EXPECTED_IRR": (0.01, "absolute"),
    "EXPECTED_CAGR": (0.01, "absolute"),
}

_RISK_BY_RULE: dict[str, str] = {
    "ER004": "LIMITED_EXPECTED_RETURN",
    "ER005": "POOR_EXPECTED_RETURN",
    "ER006": "NEGATIVE_EXPECTED_RETURN",
    "ER008": "INDEX_SUPERIOR",
    "ER009": "PEER_SUPERIOR",
    "ER010": "VALUATION_HEADWIND",
    "ER011": "REVERSION_DOMINANCE",
    "ER012": "NEGATIVE_GROWTH_CONTRIBUTION",
    "ER015": "ELEVATED_DIVIDEND_YIELD",
    "ER016": "UNSUSTAINABLE_BUYBACKS",
    "ER017": "DIVIDEND_GROWTH_UNSUSTAINABLE",
    "ER018": "FCF_GROWTH_LAG",
    "ER022": "BEAR_RETURN_NEGATIVE",
    "ER024": "WIDE_RETURN_SPREAD",
    "ER025": "WORKBOOK_IRR_DIVERGENCE",
    "ER026": "WORKBOOK_CAGR_DIVERGENCE",
    "ER030": "INSUFFICIENT_RETURN_EVIDENCE",
}

_OPP_BY_RULE: dict[str, str] = {
    "ER001": "EXCELLENT_EXPECTED_RETURN",
    "ER002": "ATTRACTIVE_EXPECTED_RETURN",
    "ER007": "SUPERIOR_VS_INDEX",
    "ER013": "DIVIDEND_YIELD_SUPPORT",
    "ER014": "BUYBACK_YIELD_SUPPORT",
    "ER023": "BULL_RETURN_EXCEPTIONAL",
    "ER027": "WORKBOOK_RETURN_ALIGNED",
}


class ExpectedReturnModule(AnalysisModule):
    """Estimate forward shareholder return and emit the Expected Return Score."""

    module_id = "expected_return"
    module_version = "1.0.0"

    def analyze(
        self,
        model: CompanyFinancialModel,
        valuation_compute: ValuationComputeResult | None = None,
    ) -> AnalysisModuleResult:
        compute = compute_expected_return(model, valuation=valuation_compute)
        has_price = compute.share_price is not None and compute.share_price > 0

        if not has_price and not compute.valuation_available:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={
                    "expected_return": False,
                    "skip_reason": "missing_price_and_valuation",
                    "assumptions": [a.to_dict() for a in compute.assumptions],
                },
                error="Insufficient inputs for expected return (price and fair value missing).",
            )

        period = model.periods[-1] if model.periods else None
        currency = model.reporting_currency
        metrics, evidence_by_metric = self._build_metrics(compute, period, currency)
        comparison_bundle = self._build_comparisons(model, metrics, period)
        comparison_statuses = {
            _WORKBOOK_CODE_MAP.get(c.metric_code, c.metric_code): c.status
            for c in comparison_bundle.comparisons
        }

        buybacks_exceed_fcf = _buybacks_exceed_fcf(model)
        dividend_cagr = _dividend_cagr(model)

        rule_hits = evaluate_expected_return_rules(
            ExpectedReturnRuleInputs(
                expected_cagr=compute.expected_cagr,
                expected_irr=compute.expected_irr,
                growth_contribution=compute.growth_contribution,
                dividend_yield=compute.dividend_yield,
                buyback_yield=compute.buyback_yield,
                valuation_reversion=compute.valuation_reversion,
                multiple_expansion=compute.multiple_expansion,
                sp500_expected_return=compute.sp500_expected_return,
                peer_expected_return=compute.peer_expected_return,
                holding_period_years=compute.holding_period_years,
                valuation_available=compute.valuation_available,
                share_price_available=has_price,
                dividend_cagr=dividend_cagr,
                eps_growth=compute.eps_growth_contribution,
                fcf_growth=compute.fcf_growth_contribution,
                buybacks_exceed_fcf=buybacks_exceed_fcf,
                scenario_bear_cagr=compute.scenarios.get("bear").expected_cagr
                if compute.scenarios.get("bear")
                else None,
                scenario_bull_cagr=compute.scenarios.get("bull").expected_cagr
                if compute.scenarios.get("bull")
                else None,
                comparison_statuses=comparison_statuses,
                workbook_return_present=_workbook_return_present(model),
                hap_return_computable=compute.expected_cagr is not None,
                period=period,
                evidence_by_metric=evidence_by_metric,
            )
        )
        findings = [hit.to_finding() for hit in rule_hits]
        rule_ids = {f.rule_id for f in findings if f.rule_id}
        risks, opportunities = self._risks_and_opportunities(findings)
        adjustments = self._adjustment_proposals(findings, compute, comparison_bundle)

        confidence_penalty = compute.confidence_penalty
        if comparison_bundle.divergent_count > 0:
            confidence_penalty += min(0.15, 0.08 * comparison_bundle.divergent_count)
        if compute.valuation_reversion is not None and compute.expected_cagr and compute.expected_cagr > 0:
            if compute.valuation_reversion / compute.expected_cagr > 0.60:
                confidence_penalty += 0.06
        confidence_boost = 0.05 if "ER027" in rule_ids else 0.0

        score_result = score_expected_return(
            ExpectedReturnScoreInputs(
                growth_contribution=compute.growth_contribution,
                dividend_yield=compute.dividend_yield,
                buyback_yield=compute.buyback_yield,
                valuation_reversion=compute.valuation_reversion,
                multiple_expansion=compute.multiple_expansion,
                expected_cagr=compute.expected_cagr,
                period=period,
                evidence=evidence_by_metric,
                input_confidence=_assumption_confidences(compute),
                confidence_penalty=confidence_penalty - confidence_boost,
            )
        )

        evidence_bag: list[Evidence] = []
        for metric in metrics:
            evidence_bag.extend(metric.evidence)
        for finding in findings:
            evidence_bag.extend(finding.evidence)

        coverage: dict[str, Any] = {
            "expected_return": True,
            "holding_period_years": compute.holding_period_years,
            "valuation_consumed": compute.valuation_available,
            "valuation_method_count": compute.valuation_method_count,
            "valuation_methods_used": compute.valuation_methods_used,
            "valuation_source": "hap_valuation_engine",
            "assumptions": [a.to_dict() for a in compute.assumptions],
            "scenarios": {
                name: {
                    "expected_cagr": s.expected_cagr,
                    "expected_irr": s.expected_irr,
                    "valuation_reversion": s.valuation_reversion,
                    "fair_value_per_share": s.fair_value_per_share,
                }
                for name, s in compute.scenarios.items()
            },
            "effective_weights": score_result.effective_weights,
            "sp500_hurdle": compute.sp500_expected_return,
            "expected_return_confidence_cap": EXPECTED_RETURN_CONFIDENCE_CAP,
        }
        coverage = attach_metric_comparisons(coverage, comparison_bundle)

        if compute.expected_cagr is None:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="ok",
                score=None,
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

    def _build_metrics(
        self,
        compute: Any,
        period: str | None,
        currency: str,
    ) -> tuple[list[MetricResult], dict[str, list[Evidence]]]:
        metrics: list[MetricResult] = []
        evidence_by_metric: dict[str, list[Evidence]] = {}

        def _assumption_evidence(code: str) -> list[Evidence]:
            for record in compute.assumptions:
                if record.code == code:
                    return [
                        Evidence(
                            kind="derived_metric",
                            label=code,
                            metric=code,
                            period=period,
                            value=record.value,
                            unit=record.unit,
                            source=record.source,
                            source_document=record.source_document,
                            confidence=record.confidence,
                            provenance=record.provenance,
                            details={"assumption": True},
                        )
                    ]
            return []

        def _add(
            code: str,
            name: str,
            value: float | None,
            unit: str,
            *,
            assumption_code: str | None = None,
        ) -> None:
            if value is None:
                return
            ev = _assumption_evidence(assumption_code or code) or [
                Evidence(
                    kind="derived_metric",
                    label=name,
                    metric=code,
                    period=period,
                    value=value,
                    unit=unit,
                    source="hap_derived",
                    confidence=0.85,
                )
            ]
            evidence_by_metric[code] = ev
            metrics.append(
                MetricResult(
                    name=name,
                    code=code,
                    value=value,
                    unit=unit,
                    period=period,
                    confidence=ev[0].confidence if ev else 0.85,
                    evidence=ev,
                )
            )

        _add("EXPECTED_CAGR", "Expected CAGR", compute.expected_cagr, "ratio")
        _add("EXPECTED_IRR", "Expected IRR", compute.expected_irr, "ratio")
        _add("GROWTH_CONTRIBUTION", "Growth Contribution", compute.growth_contribution, "ratio")
        _add("EPS_GROWTH_CONTRIBUTION", "EPS Growth Contribution", compute.eps_growth_contribution, "ratio")
        _add("FCF_GROWTH_CONTRIBUTION", "FCF Growth Contribution", compute.fcf_growth_contribution, "ratio")
        _add("DIVIDEND_YIELD", "Dividend Yield", compute.dividend_yield, "ratio")
        _add("BUYBACK_YIELD", "Buyback Yield", compute.buyback_yield, "ratio")
        _add("VALUATION_REVERSION", "Valuation Reversion", compute.valuation_reversion, "ratio")
        _add("MULTIPLE_EXPANSION", "Multiple Expansion", compute.multiple_expansion, "ratio")
        _add("MARGIN_OF_SAFETY", "Margin of Safety", compute.margin_of_safety, "ratio")
        _add("FAIR_VALUE_BASE", "Fair Value Base", compute.fair_value_base, currency)
        _add("SHARE_PRICE", "Share Price", compute.share_price, currency)
        _add(
            "SP500_EXPECTED_RETURN",
            "S&P 500 Expected Return Hurdle",
            compute.sp500_expected_return,
            "ratio",
            assumption_code="SP500_EXPECTED_RETURN",
        )
        if compute.peer_expected_return is not None:
            _add(
                "PEER_EXPECTED_RETURN",
                "Peer Expected Return Hurdle",
                compute.peer_expected_return,
                "ratio",
                assumption_code="PEER_EXPECTED_RETURN",
            )

        for name, scenario in compute.scenarios.items():
            _add(
                f"SCENARIO_{name.upper()}_EXPECTED_CAGR",
                f"{name.title()} Scenario Expected CAGR",
                scenario.expected_cagr,
                "ratio",
            )
            _add(
                f"SCENARIO_{name.upper()}_EXPECTED_IRR",
                f"{name.title()} Scenario Expected IRR",
                scenario.expected_irr,
                "ratio",
            )

        return metrics, evidence_by_metric

    def _build_comparisons(
        self,
        model: CompanyFinancialModel,
        metrics: list[MetricResult],
        period: str | None,
    ) -> ModuleMetricComparisons:
        catalog = model.workbook_metrics
        comparisons = []
        for metric in metrics:
            if metric.code not in _ER_COMPARABLE_CODES:
                continue
            workbook_code = _WORKBOOK_CODE_MAP.get(metric.code, metric.code)
            target_period = period or metric.period
            workbook_metric = catalog.get(workbook_code, period=target_period)
            tol, mode = _COMPARISON_TOLERANCE.get(metric.code, (0.01, "absolute"))
            comparisons.append(
                compare_workbook_to_hap(
                    comparison_id=f"{self.module_id}:cmp:{metric.code}:{target_period or 'latest'}",
                    metric_code=metric.code,
                    metric_name=metric.name,
                    module_name=self.module_id,
                    workbook=workbook_metric,
                    hap=metric,
                    period=target_period,
                    unit=metric.unit,
                    tolerance=tol,
                    tolerance_mode=mode,
                )
            )
        divergent = sum(1 for item in comparisons if item.status == "divergent")
        return ModuleMetricComparisons(
            comparisons=comparisons,
            workbook_metric_count=sum(1 for item in comparisons if item.workbook_value is not None),
            hap_metric_count=sum(1 for item in comparisons if item.hap_value is not None),
            divergent_count=divergent,
        )

    def _risks_and_opportunities(
        self,
        findings: list[Finding],
    ) -> tuple[list[RiskItem], list[OpportunityItem]]:
        risks: list[RiskItem] = []
        opportunities: list[OpportunityItem] = []
        for finding in findings:
            rule_id = finding.rule_id or ""
            if finding.severity in {"warning", "critical", "high", "medium"}:
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
            if finding.severity in {"positive", "info"} and finding.direction == "positive":
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
        compute: Any,
        comparison_bundle: ModuleMetricComparisons,
    ) -> list[AnalystAdjustmentProposal]:
        adjustments: list[AnalystAdjustmentProposal] = []
        finding_ids = {f.rule_id: f.finding_id for f in findings if f.rule_id}

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
                    adjustment_id=f"expected_return:adj:{action}:{rule_id.lower()}",
                    action=action,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale_code=rationale,
                    target=target,
                    related_finding_ids=[finding_ids[rule_id]],
                    confidence=0.75,
                )
            )

        _add("ER004", "review_assumption", "REVISE_GROWTH_ASSUMPTIONS", "metadata.expected_return.expected_eps_growth")
        _add("ER005", "review_assumption", "REVISE_VALUATION_ASSUMPTIONS", "valuation_inputs.wacc", "high")
        _add("ER006", "review_assumption", "REVISE_ENTRY_PRICE", "market_data.share_price", "high")
        _add("ER008", "review_assumption", "COMPARE_INDEX_HURDLE", "metadata.expected_return.sp500_expected_return")
        _add("ER010", "review_assumption", "REVISE_FAIR_VALUE", "metadata.valuation.forecast_revenue_growth", "high")
        _add("ER012", "adjust_forecast", "REVISE_GROWTH_ASSUMPTIONS", "metadata.expected_return.expected_fcf_growth")
        _add("ER015", "review_assumption", "REVIEW_PAYOUT_POLICY", "cash_flow_statement.dividends")
        _add("ER016", "review_assumption", "REVIEW_BUYBACK_POLICY", "cash_flow_statement.share_repurchases")
        _add("ER019", "request_more_data", "MISSING_VALUATION_INPUTS", "valuation_inputs.wacc", "high")
        _add("ER020", "request_more_data", "MISSING_MARKET_DATA", "market_data.share_price", "high")
        _add("ER022", "adjust_forecast", "STRESS_BEAR_CASE", "metadata.valuation.scenarios.bear", "high")
        _add("ER024", "review_assumption", "RECONCILE_SCENARIOS", "metadata.valuation.scenarios")
        _add("ER025", "reconcile_inputs", "WORKBOOK_HAP_DIVERGENCE", "workbook_metrics.EXPECTED_IRR")
        _add("ER026", "reconcile_inputs", "WORKBOOK_HAP_DIVERGENCE", "workbook_metrics.EXPECTED_CAGR")
        _add("ER028", "request_more_data", "MISSING_RETURN_INPUTS", "metadata.expected_return")
        _add("ER029", "review_assumption", "REVISE_HOLDING_PERIOD", "metadata.expected_return.holding_period_years")
        _add("ER030", "request_more_data", "MISSING_RETURN_INPUTS", "market_data.share_price", "high")

        return adjustments


def _buybacks_exceed_fcf(model: CompanyFinancialModel) -> bool:
    cfs = model.cash_flow_statement
    buybacks = cfs.share_repurchases.latest()
    fcf = cfs.free_cash_flow.latest()
    if buybacks is None or fcf is None or fcf.value <= 0:
        return False
    return abs(buybacks.value) > fcf.value


def _dividend_cagr(model: CompanyFinancialModel) -> float | None:
    series = model.cash_flow_statement.dividends
    if len(series) < 2:
        return None
    return series.cagr(TREND_WINDOW)


def _workbook_return_present(model: CompanyFinancialModel) -> bool:
    catalog = model.workbook_metrics
    return catalog.get("EXPECTED_IRR") is not None or catalog.get("EXPECTED_CAGR") is not None


def _assumption_confidences(compute: Any) -> dict[str, float]:
    return {
        "GROWTH_CONTRIBUTION": 0.80,
        "DIVIDEND_YIELD": 0.85,
        "BUYBACK_YIELD": 0.80,
        "VALUATION_REVERSION": 0.75 if compute.valuation_available else 0.55,
        "MULTIPLE_EXPANSION": 0.70,
        "EXPECTED_CAGR_LEVEL": 0.85 if compute.expected_cagr is not None else 0.50,
    }


def _unique_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[Evidence] = []
    for item in items:
        key = (item.metric, item.period, item.value, item.source)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
