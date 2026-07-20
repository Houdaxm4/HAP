"""Enterprise Valuation analysis module — ENTERPRISE_VALUATION_MODULE_SPEC.md.

Consumes only ``CompanyFinancialModel``. Computes independent HAP valuations,
compares to workbook metrics, and emits the Valuation Score with VA001–VA038.
"""

from __future__ import annotations

from typing import Any

from analysis_engine.base import AnalysisModule
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
from analysis_engine.utils import mean, safe_div
from analysis_engine.valuation_engine import ValuationComputeResult, compute_valuation
from canonical_model import CompanyFinancialModel
from rule_library.valuation import ValuationRuleInputs, evaluate_valuation_rules
from scoring_engine.valuation import VALUATION_CONFIDENCE_CAP, ValuationScoreInputs, score_valuation

_VALUATION_COMPARABLE_CODES = frozenset(
    {
        "HAP_ENTERPRISE_VALUE",
        "HAP_EQUITY_VALUE",
        "HAP_INTRINSIC_VALUE_PER_SHARE",
        "FAIR_VALUE_BASE",
        "MARGIN_OF_SAFETY",
        "WACC_ASSUMPTION",
        "TERMINAL_GROWTH_ASSUMPTION",
    }
)

_WORKBOOK_CODE_MAP: dict[str, str] = {
    "HAP_ENTERPRISE_VALUE": "ENTERPRISE_VALUE",
    "HAP_EQUITY_VALUE": "EQUITY_VALUE",
    "HAP_INTRINSIC_VALUE_PER_SHARE": "INTRINSIC_VALUE",
    "FAIR_VALUE_BASE": "FAIR_VALUE",
    "MARGIN_OF_SAFETY": "MARGIN_OF_SAFETY",
    "WACC_ASSUMPTION": "WACC",
    "TERMINAL_GROWTH_ASSUMPTION": "TERMINAL_GROWTH",
}

_COMPARISON_TOLERANCE: dict[str, tuple[float, ToleranceMode]] = {
    "HAP_ENTERPRISE_VALUE": (0.05, "relative"),
    "HAP_EQUITY_VALUE": (0.05, "relative"),
    "HAP_INTRINSIC_VALUE_PER_SHARE": (0.05, "relative"),
    "FAIR_VALUE_BASE": (0.05, "relative"),
    "MARGIN_OF_SAFETY": (0.03, "absolute"),
    "WACC_ASSUMPTION": (0.0075, "absolute"),
    "TERMINAL_GROWTH_ASSUMPTION": (0.005, "absolute"),
}

_RISK_BY_RULE: dict[str, str] = {
    "VA003": "LIMITED_UPSIDE",
    "VA004": "POTENTIAL_OVERVALUATION",
    "VA005": "AGGRESSIVE_IMPLIED_GROWTH",
    "VA008": "WACC_TOO_LOW",
    "VA009": "WACC_TOO_HIGH",
    "VA010": "WACC_INCONSISTENT",
    "VA011": "TERMINAL_GROWTH_ABOVE_GDP",
    "VA012": "UNSUSTAINABLE_TERMINAL_GROWTH",
    "VA013": "DECLINING_TERMINAL_STATE",
    "VA014": "TERMINAL_VALUE_DOMINANCE",
    "VA016": "NEGATIVE_FCF_FORECAST",
    "VA018": "BEAR_CASE_BELOW_MARKET",
    "VA019": "VALUATION_DISPERSION",
    "VA021": "MULTIPLE_ABOVE_PEERS",
    "VA024": "HISTORICAL_MULTIPLE_EXTREME",
    "VA026": "OWNER_EARNINGS_GAP",
    "VA028": "NET_DEBT_UNCERTAINTY",
    "VA029": "LEVERAGE_AMPLIFIES_ERROR",
    "VA030": "WORKBOOK_IV_DIVERGENCE",
    "VA031": "WORKBOOK_MOS_DIVERGENCE",
    "VA032": "WORKBOOK_WACC_DIVERGENCE",
    "VA033": "WORKBOOK_TG_DIVERGENCE",
    "VA036": "CYCLICAL_PEAK_EARNINGS",
    "VA037": "DISTRESSED_VALUATION",
    "VA038": "INSUFFICIENT_VALUATION_INPUTS",
}

_OPP_BY_RULE: dict[str, str] = {
    "VA001": "HIGHLY_ATTRACTIVE_VALUATION",
    "VA002": "ATTRACTIVE_VALUATION",
    "VA006": "MARKET_PESSIMISM",
    "VA022": "DISCOUNT_TO_PEERS",
    "VA025": "HISTORICAL_DISCOUNT",
    "VA027": "OWNER_EARNINGS_CONFIRMS_DCF",
    "VA034": "WORKBOOK_ALIGNED",
}


class ValuationModule(AnalysisModule):
    """Independent enterprise valuation synthesis and workbook comparison."""

    module_id = "valuation"
    module_version = "1.0.0"

    def analyze(
        self,
        model: CompanyFinancialModel,
        valuation_compute: ValuationComputeResult | None = None,
    ) -> AnalysisModuleResult:
        cfs = model.cash_flow_statement
        has_fcf = not cfs.free_cash_flow.is_empty or (
            not cfs.operating_cash_flow.is_empty and not cfs.capital_expenditures.is_empty
        )
        has_price = model.market_data.share_price is not None

        if not has_fcf and not has_price:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={"valuation": False, "skip_reason": "missing_fcf_and_price"},
                error="Insufficient valuation inputs (FCF and share price missing).",
            )

        compute = valuation_compute if valuation_compute is not None else compute_valuation(model)
        if compute.method_count < 1:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={
                    "valuation": False,
                    "skip_reason": "no_valuation_methods",
                    "assumptions": [a.to_dict() for a in compute.assumptions],
                },
                error="No valuation method could be computed.",
            )

        period = model.periods[-1] if model.periods else None
        currency = model.reporting_currency
        metrics, evidence_by_metric = self._build_metrics(compute, model, period, currency)
        comparison_bundle = self._build_comparisons(model, metrics, period)
        comparison_statuses = {
            _WORKBOOK_CODE_MAP.get(c.metric_code, c.metric_code): c.status
            for c in comparison_bundle.comparisons
        }

        margin_vs_10y = _operating_margin_vs_median(model)
        negative_fcf_years = _count_negative_fcf_years(model)
        net_debt_uncertain = (
            model.valuation_inputs.net_debt is None
            and (
                model.balance_sheet.total_debt.is_empty or model.balance_sheet.cash.is_empty
            )
        )
        net_debt_to_ev = (
            safe_div(compute.net_debt, compute.hap_enterprise_value)
            if compute.net_debt is not None and compute.hap_enterprise_value
            else None
        )
        equity_sensitivity = _equity_sensitivity_high(
            compute.hap_enterprise_value,
            compute.net_debt,
            compute.hap_equity_value,
        )

        dcf_method = compute.methods.get("dcf")
        oe_method = compute.methods.get("owner_earnings")
        reverse_unrealistic = (
            compute.reverse_dcf_implied_growth is not None
            and (
                compute.reverse_dcf_implied_growth > compute.gdp_growth + 0.06
            )
        )

        rule_hits = evaluate_valuation_rules(
            ValuationRuleInputs(
                margin_of_safety=compute.margin_of_safety,
                fair_value_base=compute.fair_value_base,
                share_price=compute.share_price,
                reverse_dcf_implied_growth=compute.reverse_dcf_implied_growth,
                reverse_dcf_implied_fcf_cagr=None,
                reverse_dcf_solvable=compute.reverse_dcf_solvable,
                wacc=compute.wacc,
                risk_free_rate=model.valuation_inputs.risk_free_rate,
                terminal_growth=compute.terminal_growth,
                gdp_growth=compute.gdp_growth,
                dcf_terminal_share=dcf_method.dcf_terminal_share if dcf_method else None,
                forecast_years=compute.forecast_years,
                negative_forecast_fcf=bool(dcf_method and dcf_method.negative_forecast_fcf),
                turnaround_plan=compute.turnaround_plan,
                dcf_available=compute.dcf_available,
                scenario_bear_value=compute.scenarios.get("bear").value_per_share
                if compute.scenarios.get("bear")
                else None,
                method_spread=compute.method_spread,
                method_count=compute.method_count,
                implied_ev_to_ebitda=compute.implied_ev_to_ebitda,
                peer_p25=compute.peer_p25,
                peer_p75=compute.peer_p75,
                peer_median=compute.peer_median,
                historical_median_multiple=compute.historical_median_multiple,
                multiples_method_available="multiples" in compute.methods,
                owner_earnings_run_rate=compute.owner_earnings_run_rate,
                latest_net_income=compute.latest_net_income,
                oe_value_per_share=oe_method.value_per_share if oe_method else None,
                dcf_value_per_share=dcf_method.value_per_share if dcf_method else None,
                net_debt_uncertain=net_debt_uncertain,
                net_debt_to_ev=net_debt_to_ev,
                equity_sensitivity_high=equity_sensitivity,
                cyclicality_flag=compute.cyclicality_flag,
                margin_vs_10y_median=margin_vs_10y,
                negative_fcf_years=negative_fcf_years,
                hap_equity_value=compute.hap_equity_value,
                comparison_statuses=comparison_statuses,
                workbook_valuation_present=_workbook_valuation_present(model),
                hap_valuation_computable=compute.fair_value_base is not None,
                period=period,
                evidence_by_metric=evidence_by_metric,
            )
        )
        findings = [hit.to_finding() for hit in rule_hits]
        rule_ids = {f.rule_id for f in findings if f.rule_id}
        risks, opportunities = self._risks_and_opportunities(findings)
        adjustments = self._adjustment_proposals(findings, compute, comparison_bundle)

        confidence_penalty = compute.confidence_penalty
        if compute.method_count < 2:
            confidence_penalty += 0.12
        if compute.method_spread is not None and compute.method_spread > 0.40:
            confidence_penalty += 0.12
        if comparison_bundle.divergent_count > 0:
            confidence_penalty += min(0.20, 0.08 * comparison_bundle.divergent_count)
        if dcf_method and dcf_method.dcf_terminal_share and dcf_method.dcf_terminal_share > 0.75:
            confidence_penalty += 0.06
        if compute.peer_median is None:
            confidence_penalty += 0.05
        if compute.cyclicality_flag and margin_vs_10y is not None and margin_vs_10y > 1.20:
            confidence_penalty += 0.08

        confidence_boost = 0.0
        if compute.method_spread is not None and compute.method_spread <= 0.15 and compute.method_count >= 3:
            confidence_boost += 0.05
        if "VA034" in rule_ids:
            confidence_boost += 0.05
        if "VA027" in rule_ids:
            confidence_boost += 0.03

        divergent_count = comparison_bundle.divergent_count
        comparable_count = sum(
            1
            for c in comparison_bundle.comparisons
            if c.workbook_value is not None and c.hap_value is not None
        )
        workbook_only_count = sum(
            1 for c in comparison_bundle.comparisons if c.status == "workbook_only"
        )
        all_within = comparable_count > 0 and divergent_count == 0

        score_result = score_valuation(
            ValuationScoreInputs(
                margin_of_safety=compute.margin_of_safety if has_price else None,
                terminal_share=dcf_method.dcf_terminal_share if dcf_method else None,
                terminal_growth=compute.terminal_growth,
                gdp_growth=compute.gdp_growth,
                wacc=compute.wacc,
                forecast_years=compute.forecast_years,
                reverse_dcf_unrealistic=reverse_unrealistic,
                implied_multiple=compute.implied_ev_to_ebitda,
                peer_p25=compute.peer_p25,
                peer_median=compute.peer_median,
                peer_p75=compute.peer_p75,
                historical_median=compute.historical_median_multiple,
                method_spread=compute.method_spread,
                divergent_count=divergent_count,
                comparable_count=comparable_count,
                workbook_only_count=workbook_only_count,
                all_within_tolerance=all_within,
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
            "valuation": True,
            "methods_used": list(compute.methods.keys()),
            "method_count": compute.method_count,
            "dcf_available": compute.dcf_available,
            "assumptions": [a.to_dict() for a in compute.assumptions],
            "scenarios": {
                name: {
                    "value_per_share": s.value_per_share,
                    "margin_of_safety": s.margin_of_safety,
                }
                for name, s in compute.scenarios.items()
            },
            "effective_weights": score_result.effective_weights,
            "share_price_available": has_price,
            "valuation_confidence_cap": VALUATION_CONFIDENCE_CAP,
        }
        coverage = attach_metric_comparisons(coverage, comparison_bundle)

        status = "ok"
        final_score = score_result.score if has_price else None
        if "VA038" in rule_ids and not has_price:
            status = "ok"

        return AnalysisModuleResult(
            module_name=self.module_id,
            module_version=self.module_version,
            status=status,
            score=final_score,
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
        model: CompanyFinancialModel,
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

        dcf = compute.methods.get("dcf")
        oe = compute.methods.get("owner_earnings")
        mult = compute.methods.get("multiples")
        hist = compute.methods.get("historical")

        if dcf:
            _add("DCF_ENTERPRISE_VALUE", "DCF Enterprise Value", dcf.enterprise_value, currency)
            _add("DCF_EQUITY_VALUE", "DCF Equity Value", dcf.equity_value, currency)
            _add("DCF_VALUE_PER_SHARE", "DCF Value Per Share", dcf.value_per_share, currency)
            _add("DCF_TERMINAL_VALUE_SHARE", "DCF Terminal Value Share", dcf.dcf_terminal_share, "ratio")
            _add("DCF_PV_FORECAST_SHARE", "DCF PV Forecast Share", dcf.dcf_pv_forecast_share, "ratio")
        if oe:
            _add("OE_ENTERPRISE_VALUE", "Owner Earnings EV", oe.enterprise_value, currency)
            _add("OE_EQUITY_VALUE", "Owner Earnings Equity", oe.equity_value, currency)
            _add("OE_VALUE_PER_SHARE", "Owner Earnings Per Share", oe.value_per_share, currency)
        if mult:
            _add("MULTIPLE_VALUE_PER_SHARE", "Multiple Value Per Share", mult.value_per_share, currency)
            _add("MULTIPLE_EV_EBITDA", "Implied EV/EBITDA Multiple", mult.implied_multiple, "ratio")
        if hist:
            _add("HIST_VALUE_PER_SHARE", "Historical Multiple Value Per Share", hist.value_per_share, currency)

        _add("OWNER_EARNINGS_RUN_RATE", "Owner Earnings Run Rate", compute.owner_earnings_run_rate, currency)
        _add("HAP_ENTERPRISE_VALUE", "HAP Enterprise Value", compute.hap_enterprise_value, currency)
        _add("HAP_EQUITY_VALUE", "HAP Equity Value", compute.hap_equity_value, currency)
        _add(
            "HAP_INTRINSIC_VALUE_PER_SHARE",
            "HAP Intrinsic Value Per Share",
            compute.hap_intrinsic_value_per_share,
            currency,
        )
        _add("FAIR_VALUE_BASE", "Fair Value Base", compute.fair_value_base, currency)
        _add("FAIR_VALUE_LOW", "Fair Value Low", compute.fair_value_low, currency)
        _add("FAIR_VALUE_HIGH", "Fair Value High", compute.fair_value_high, currency)
        _add("MARGIN_OF_SAFETY", "Margin of Safety", compute.margin_of_safety, "ratio")
        _add("PREMIUM_DISCOUNT", "Premium / Discount", compute.premium_discount, "ratio")
        _add("METHOD_SPREAD", "Method Spread", compute.method_spread, "ratio")
        _add(
            "REVERSE_DCF_IMPLIED_GROWTH",
            "Reverse DCF Implied Growth",
            compute.reverse_dcf_implied_growth,
            "ratio",
        )
        _add("IMPLIED_EV_EBITDA", "Implied EV/EBITDA", compute.implied_ev_to_ebitda, "ratio")
        _add("WACC_ASSUMPTION", "WACC Assumption", compute.wacc, "ratio", assumption_code="WACC")
        _add(
            "TERMINAL_GROWTH_ASSUMPTION",
            "Terminal Growth Assumption",
            compute.terminal_growth,
            "ratio",
            assumption_code="TERMINAL_GROWTH",
        )
        _add("VALUATION_CONFIDENCE", "Valuation Confidence", compute.method_count / 4.0, "ratio")

        for name, scenario in compute.scenarios.items():
            code = f"SCENARIO_{name.upper()}_VALUE_PER_SHARE"
            _add(code, f"{name.title()} Scenario Value Per Share", scenario.value_per_share, currency)
            mos_code = f"SCENARIO_MOS_{name.upper()}"
            _add(mos_code, f"{name.title()} Scenario MOS", scenario.margin_of_safety, "ratio")

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
            if metric.code not in _VALUATION_COMPARABLE_CODES:
                continue
            workbook_code = _WORKBOOK_CODE_MAP.get(metric.code, metric.code)
            target_period = period or metric.period
            workbook_metric = catalog.get(workbook_code, period=target_period)
            tol, mode = _COMPARISON_TOLERANCE.get(metric.code, (0.05, "relative"))
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
                    adjustment_id=f"valuation:adj:{action}:{rule_id.lower()}",
                    action=action,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale_code=rationale,
                    target=target,
                    related_finding_ids=[finding_ids[rule_id]],
                    confidence=0.75,
                )
            )

        _add("VA008", "review_assumption", "REVISE_WACC", "valuation_inputs.wacc", "high")
        _add("VA009", "review_assumption", "REVISE_WACC", "valuation_inputs.wacc", "high")
        _add("VA010", "review_assumption", "REVISE_WACC", "valuation_inputs.wacc", "high")
        _add("VA011", "review_assumption", "REVISE_TERMINAL_GROWTH", "valuation_inputs.terminal_growth_rate")
        _add("VA012", "review_assumption", "REVISE_TERMINAL_GROWTH", "valuation_inputs.terminal_growth_rate", "high")
        _add("VA014", "adjust_forecast", "REVISE_FORECAST_GROWTH", "metadata.valuation.forecast_revenue_growth")
        _add("VA016", "adjust_forecast", "REVISE_FORECAST_MARGINS", "metadata.valuation.forecast_operating_margin", "high")
        _add("VA021", "review_assumption", "REVIEW_PEER_MULTIPLES", "metadata.valuation.peer_ev_to_ebitda")
        _add("VA023", "request_more_data", "MISSING_PEER_DATA", "metadata.valuation.peer_ev_to_ebitda")
        _add("VA026", "request_more_data", "MISSING_MAINTENANCE_CAPEX", "metadata.valuation.maintenance_capex")
        _add("VA028", "review_assumption", "REVIEW_CAPITAL_STRUCTURE", "valuation_inputs.net_debt")
        _add("VA030", "reconcile_inputs", "WORKBOOK_HAP_DIVERGENCE", "workbook_metrics.INTRINSIC_VALUE")
        _add("VA031", "reconcile_inputs", "WORKBOOK_HAP_DIVERGENCE", "workbook_metrics.MARGIN_OF_SAFETY")
        _add("VA032", "investigate_workbook_formula", "WORKBOOK_FORMULA_REVIEW", "workbook_metrics.WACC")
        _add("VA033", "investigate_workbook_formula", "WORKBOOK_FORMULA_REVIEW", "workbook_metrics.TERMINAL_GROWTH")
        _add("VA035", "request_more_data", "MISSING_MARKET_DATA", "market_data.share_price")
        _add("VA036", "review_assumption", "NORMALIZE_CYCLICAL_EARNINGS", "metadata.valuation.normalized_ebitda", "high")
        _add("VA037", "request_analyst_review", "VALUATION_UNCERTAINTY", "valuation", "high")
        _add("VA038", "request_more_data", "MISSING_MARKET_DATA", "market_data.share_price", "high")

        for comparison in comparison_bundle.comparisons:
            if comparison.status == "divergent" and comparison.recommended_action == "investigate_workbook_formula":
                adjustments.append(
                    AnalystAdjustmentProposal(
                        adjustment_id=f"valuation:adj:formula:{comparison.metric_code.lower()}",
                        action="investigate_workbook_formula",
                        priority="medium",
                        rationale_code="WORKBOOK_FORMULA_REVIEW",
                        target=comparison.workbook_metric.get("cell_ref", comparison.metric_code)
                        if comparison.workbook_metric
                        else comparison.metric_code,
                        related_finding_ids=[
                            finding_ids.get("VA030", finding_ids.get("VA032", "")),
                        ]
                        if finding_ids.get("VA030") or finding_ids.get("VA032")
                        else [],
                        confidence=0.80,
                    )
                )
        return adjustments


def _operating_margin_vs_median(model: CompanyFinancialModel) -> float | None:
    income = model.income_statement
    margins: list[float] = []
    for period in income.revenue.periods():
        rev = income.revenue.point_for(period)
        oi = income.operating_income.point_for(period) or income.ebit.point_for(period)
        if rev is None or oi is None or rev.value == 0:
            continue
        margins.append(oi.value / rev.value)
    if not margins:
        return None
    latest = margins[-1]
    median = sorted(margins)[len(margins) // 2]
    if median == 0:
        return None
    return latest / median


def _count_negative_fcf_years(model: CompanyFinancialModel) -> int:
    cfs = model.cash_flow_statement
    if not cfs.free_cash_flow.is_empty:
        series = cfs.free_cash_flow
    else:
        return 0
    return sum(1 for p in series.points if p.value < 0)


def _equity_sensitivity_high(
    ev: float | None,
    net_debt: float | None,
    equity: float | None,
) -> bool:
    if ev is None or net_debt is None or equity is None or ev == 0 or equity == 0:
        return False
    if net_debt / ev <= 0.50:
        return False
    perturbed_equity = ev * 1.10 - net_debt
    delta = abs(perturbed_equity - equity) / abs(equity)
    return delta > 0.15


def _workbook_valuation_present(model: CompanyFinancialModel) -> bool:
    catalog = model.workbook_metrics
    for code in ("INTRINSIC_VALUE", "FAIR_VALUE", "ENTERPRISE_VALUE", "MARGIN_OF_SAFETY"):
        if catalog.get(code) is not None:
            return True
    return False


def _assumption_confidences(compute: Any) -> dict[str, float]:
    mapping = {
        "MARGIN_OF_SAFETY": 0.85,
        "DCF_REASONABLENESS": 0.80,
        "MULTIPLE_REASONABLENESS": 0.75,
        "METHOD_CONVERGENCE": 0.80,
        "WORKBOOK_ALIGNMENT": 0.70,
    }
    if compute.method_count < 2:
        mapping["METHOD_CONVERGENCE"] = 0.55
    confs = {code: rec.confidence for rec in compute.assumptions for code in (rec.code,)}
    for key in mapping:
        if key == "MARGIN_OF_SAFETY" and confs.get("WACC"):
            mapping[key] = min(0.90, mean([confs.get("WACC", 0.85), 0.85]) or 0.85)
    return mapping


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
