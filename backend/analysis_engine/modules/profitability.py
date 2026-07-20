"""Profitability analysis module — FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM.

Consumes only ``CompanyFinancialModel``. Produces a 0–100 Profitability Score
with confidence, metrics, findings (PR001–PR010), risks, opportunities,
evidence, and analyst adjustment proposals. No Excel access and no narrative.
"""

from __future__ import annotations

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
from analysis_engine.utils import (
    mean,
    paired_periods,
    point_evidence,
    ratio_series,
    safe_div,
)
from canonical_model import CompanyFinancialModel, FinancialPoint, FinancialSeries
from rule_library.profitability import evaluate_profitability_rules
from scoring_engine import ProfitabilityScoreInputs, score_profitability

TREND_WINDOW = 5

_PROFITABILITY_COMPARABLE_CODES = frozenset(
    {"ROIC", "ROE", "ROA", "GROSS_MARGIN", "OPERATING_MARGIN", "EBIT_MARGIN", "NET_MARGIN"}
)


class ProfitabilityModule(AnalysisModule):
    """Evaluate durable economic profit and emit the Profitability Score."""

    module_id = "profitability"
    module_version = "2.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        income = model.income_statement
        if income.net_income.is_empty and income.revenue.is_empty:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={"net_income": False, "revenue": False},
                error="Insufficient profitability inputs (need net income or revenue series).",
            )

        metrics: list[MetricResult] = []
        evidence_bag: list[Evidence] = []
        adjustments: list[AnalystAdjustmentProposal] = []

        # --- Core series ---
        ni_series = income.net_income
        revenue_series = income.revenue
        equity_series = model.balance_sheet.shareholders_equity
        assets_series = model.balance_sheet.total_assets
        invested_series = model.balance_sheet.invested_capital
        ebit_series = income.ebit if not income.ebit.is_empty else income.operating_income

        operating_margin_series = ratio_series(
            name="Operating Margin",
            numerator=ebit_series,
            denominator=revenue_series,
            currency="ratio",
        )
        net_margin_series = ratio_series(
            name="Net Margin",
            numerator=ni_series,
            denominator=revenue_series,
            currency="ratio",
        )
        gross_margin_series = ratio_series(
            name="Gross Margin",
            numerator=income.gross_profit,
            denominator=revenue_series,
            currency="ratio",
        )
        roe_series = ratio_series(
            name="ROE",
            numerator=ni_series,
            denominator=equity_series,
            currency="ratio",
        )
        roa_series = ratio_series(
            name="ROA",
            numerator=ni_series,
            denominator=assets_series,
            currency="ratio",
        )
        roic_series = self._build_roic_series(model)

        # Latest values
        period = (
            (ni_series.latest() or revenue_series.latest() or ebit_series.latest()).period
            if (ni_series.latest() or revenue_series.latest() or ebit_series.latest())
            else None
        )
        roic = roic_series.latest().value if roic_series.latest() else None
        roe = roe_series.latest().value if roe_series.latest() else None
        roa = roa_series.latest().value if roa_series.latest() else None
        op_margin = (
            operating_margin_series.latest().value if operating_margin_series.latest() else None
        )
        net_margin = net_margin_series.latest().value if net_margin_series.latest() else None
        gross_margin = (
            gross_margin_series.latest().value if gross_margin_series.latest() else None
        )
        margin_stability = (
            operating_margin_series.stability(TREND_WINDOW)
            if len(operating_margin_series) >= 2
            else net_margin_series.stability(TREND_WINDOW)
            if len(net_margin_series) >= 2
            else None
        )
        wacc = model.valuation_inputs.wacc

        nopat = self._latest_nopat(model)
        if nopat is not None and period:
            metrics.append(
                MetricResult(
                    name="NOPAT",
                    code="NOPAT",
                    value=nopat,
                    unit=model.reporting_currency,
                    period=period,
                    confidence=0.75,
                    evidence=[
                        Evidence(
                            kind="derived_metric",
                            label="NOPAT",
                            metric="NOPAT",
                            period=period,
                            value=nopat,
                            confidence=0.75,
                        )
                    ],
                )
            )

        for code, series in [
            ("GROSS_MARGIN", gross_margin_series),
            ("OPERATING_MARGIN", operating_margin_series),
            ("EBIT_MARGIN", operating_margin_series),
            ("NET_MARGIN", net_margin_series),
            ("ROE", roe_series),
            ("ROA", roa_series),
            ("ROIC", roic_series),
        ]:
            latest = series.latest()
            if latest is None:
                continue
            ev = [
                Evidence(
                    kind="ratio",
                    label=code,
                    metric=code,
                    period=latest.period,
                    value=latest.value,
                    unit="ratio",
                    confidence=latest.confidence,
                    source=latest.source,
                )
            ]
            evidence_bag.extend(ev)
            metrics.append(
                MetricResult(
                    name=series.name,
                    code=code if code != "EBIT_MARGIN" else "EBIT_MARGIN",
                    value=latest.value,
                    unit="ratio",
                    period=latest.period,
                    confidence=latest.confidence or 0.8,
                    evidence=ev,
                )
            )

        # Trend metrics for margins
        for series, prefix in [
            (operating_margin_series, "OPERATING_MARGIN"),
            (net_margin_series, "NET_MARGIN"),
        ]:
            if series.cagr(TREND_WINDOW) is not None:
                metrics.append(
                    MetricResult(
                        name=f"{series.name} CAGR",
                        code=f"{prefix}_CAGR",
                        value=series.cagr(TREND_WINDOW),
                        unit="ratio",
                        period=series.latest().period if series.latest() else period,
                        confidence=0.8,
                        evidence=[
                            Evidence(
                                kind="period_comparison",
                                label=f"{prefix} CAGR",
                                metric=f"{prefix}_CAGR",
                                period=series.latest().period if series.latest() else period,
                                value=series.cagr(TREND_WINDOW),
                                details={"window": TREND_WINDOW, "periods": series.periods()[-5:]},
                            )
                        ],
                    )
                )
            if series.stability(TREND_WINDOW) is not None:
                metrics.append(
                    MetricResult(
                        name=f"{series.name} Stability",
                        code=f"{prefix}_STABILITY",
                        value=series.stability(TREND_WINDOW),
                        unit="score",
                        period=series.latest().period if series.latest() else period,
                        confidence=0.8,
                        evidence=[
                            Evidence(
                                kind="period_comparison",
                                label=f"{prefix} stability",
                                metric=f"{prefix}_STABILITY",
                                value=series.stability(TREND_WINDOW),
                                period=series.latest().period if series.latest() else period,
                            )
                        ],
                    )
                )
            direction = series.trend_direction(TREND_WINDOW)
            direction_score = {"up": 1.0, "down": -1.0, "flat": 0.0}.get(direction)
            if direction_score is not None:
                metrics.append(
                    MetricResult(
                        name=f"{series.name} Trend",
                        code=f"{prefix}_TREND",
                        value=direction_score,
                        unit="direction",
                        period=series.latest().period if series.latest() else period,
                        confidence=0.75,
                        evidence=[
                            Evidence(
                                kind="period_comparison",
                                label=f"{prefix} trend",
                                metric=f"{prefix}_TREND",
                                value=direction_score,
                                period=series.latest().period if series.latest() else period,
                                details={"direction": direction},
                            )
                        ],
                        notes=direction,
                    )
                )

        evidence_by_metric = {
            "ROIC": [
                Evidence(
                    kind="ratio",
                    label="ROIC",
                    metric="ROIC",
                    value=roic,
                    period=period,
                    unit="ratio",
                )
            ]
            if roic is not None
            else [],
            "OPERATING_MARGIN": [
                Evidence(
                    kind="ratio",
                    label="Operating Margin",
                    metric="OPERATING_MARGIN",
                    value=op_margin,
                    period=period,
                    unit="ratio",
                )
            ]
            if op_margin is not None
            else [],
            "NET_MARGIN": [
                Evidence(
                    kind="ratio",
                    label="Net Margin",
                    metric="NET_MARGIN",
                    value=net_margin,
                    period=period,
                    unit="ratio",
                )
            ]
            if net_margin is not None
            else [],
            "ROE": [
                Evidence(
                    kind="ratio",
                    label="ROE",
                    metric="ROE",
                    value=roe,
                    period=period,
                    unit="ratio",
                )
            ]
            if roe is not None
            else [],
            "ROA": [
                Evidence(
                    kind="ratio",
                    label="ROA",
                    metric="ROA",
                    value=roa,
                    period=period,
                    unit="ratio",
                )
            ]
            if roa is not None
            else [],
            "MARGIN_STABILITY": [
                Evidence(
                    kind="derived_metric",
                    label="Margin Stability",
                    metric="MARGIN_STABILITY",
                    value=margin_stability,
                    period=period,
                    unit="score",
                )
            ]
            if margin_stability is not None
            else [],
        }

        score_result = score_profitability(
            ProfitabilityScoreInputs(
                roic=roic,
                operating_margin=op_margin,
                net_margin=net_margin,
                roe=roe,
                roa=roa,
                margin_stability=margin_stability,
                wacc=wacc,
                period=period,
                evidence=evidence_by_metric,
                input_confidence={
                    code: (ev[0].confidence or 0.8)
                    for code, ev in evidence_by_metric.items()
                    if ev
                },
            )
        )

        rule_hits = evaluate_profitability_rules(
            roic=roic,
            roe=roe,
            roa_series=roa_series if not roa_series.is_empty else None,
            roic_series=roic_series if not roic_series.is_empty else None,
            operating_margin_series=(
                operating_margin_series if not operating_margin_series.is_empty else None
            ),
            net_margin_series=net_margin_series if not net_margin_series.is_empty else None,
            wacc=wacc,
            period=period,
            evidence_by_metric=evidence_by_metric,
        )
        findings = [hit.to_finding() for hit in rule_hits]
        for finding in findings:
            evidence_bag.extend(finding.evidence)

        risks, opportunities = self._risks_and_opportunities(findings)
        adjustments.extend(self._adjustment_proposals(findings, gross_margin, op_margin))

        if invested_series.is_empty and ebit_series.latest() is not None:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="profitability:adj:request-invested-capital",
                    action="request_more_data",
                    priority="medium",
                    rationale_code="NEED_INVESTED_CAPITAL_FOR_ROIC",
                    target="balance_sheet.invested_capital",
                    confidence=0.85,
                )
            )

        if score_result.score is None and not metrics:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                error="Could not compute profitability metrics or score.",
            )

        coverage = {
            "roic": roic is not None,
            "operating_margin": op_margin is not None,
            "net_margin": net_margin is not None,
            "roe": roe is not None,
            "roa": roa is not None,
            "margin_stability": margin_stability is not None,
            "effective_weights": score_result.effective_weights,
            "periods_used": model.periods[-TREND_WINDOW:],
        }
        comparable_metrics = [
            metric for metric in metrics if metric.code in _PROFITABILITY_COMPARABLE_CODES
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

    def _build_roic_series(self, model: CompanyFinancialModel) -> FinancialSeries:
        income = model.income_statement
        ebit_series = income.ebit if not income.ebit.is_empty else income.operating_income
        invested = model.balance_sheet.invested_capital
        series = FinancialSeries(name="ROIC", currency="ratio")
        if ebit_series.is_empty or invested.is_empty:
            return series

        tax_series = income.tax_expense
        assumed_tax = model.valuation_inputs.tax_rate
        after_tax_default = 1.0 - assumed_tax if assumed_tax is not None else 0.75

        for period in paired_periods(ebit_series, invested):
            ebit = ebit_series.point_for(period)
            capital = invested.point_for(period)
            if ebit is None or capital is None or capital.value == 0:
                continue
            tax = tax_series.point_for(period)
            if tax is not None and ebit.value != 0:
                tax_rate = max(0.0, min(0.5, abs(tax.value) / abs(ebit.value)))
                nopat = ebit.value * (1.0 - tax_rate)
            else:
                nopat = ebit.value * after_tax_default
            roic_value = safe_div(nopat, capital.value)
            if roic_value is None:
                continue
            confidence_values = [c for c in (ebit.confidence, capital.confidence) if c is not None]
            series.upsert(
                FinancialPoint(
                    period=period,
                    value=roic_value,
                    currency="ratio",
                    source="derived",
                    confidence=mean(confidence_values),
                    audited=bool(ebit.audited and capital.audited),
                )
            )
        return series

    def _latest_nopat(self, model: CompanyFinancialModel) -> float | None:
        income = model.income_statement
        ebit = income.ebit.latest() or income.operating_income.latest()
        if ebit is None:
            return None
        tax = income.tax_expense.latest()
        if tax is not None and ebit.value != 0:
            tax_rate = max(0.0, min(0.5, abs(tax.value) / abs(ebit.value)))
            return ebit.value * (1.0 - tax_rate)
        assumed = model.valuation_inputs.tax_rate
        return ebit.value * (1.0 - assumed if assumed is not None else 0.75)

    def _risks_and_opportunities(
        self,
        findings: list[Finding],
    ) -> tuple[list[RiskItem], list[OpportunityItem]]:
        risks: list[RiskItem] = []
        opportunities: list[OpportunityItem] = []
        for finding in findings:
            if finding.severity in {"warning", "critical", "high", "medium"} and finding.direction == "negative":
                risks.append(
                    RiskItem(
                        risk_id=f"risk:{finding.finding_id}",
                        code=finding.code,
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
                        code=finding.code,
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
        gross_margin: float | None,
        op_margin: float | None,
    ) -> list[AnalystAdjustmentProposal]:
        adjustments: list[AnalystAdjustmentProposal] = []
        for finding in findings:
            if finding.rule_id == "PR008":
                adjustments.append(
                    AnalystAdjustmentProposal(
                        adjustment_id="profitability:adj:normalize-margins",
                        action="normalize_margins",
                        priority="medium",
                        rationale_code="UNSTABLE_PROFITABILITY",
                        target="income_statement.net_income",
                        related_finding_ids=[finding.finding_id],
                        confidence=0.7,
                    )
                )
            if finding.rule_id == "PR007":
                adjustments.append(
                    AnalystAdjustmentProposal(
                        adjustment_id="profitability:adj:remove-one-time",
                        action="remove_one_time",
                        priority="medium",
                        rationale_code="MARGIN_COMPRESSION",
                        target="income_statement.operating_income",
                        current_value=op_margin,
                        related_finding_ids=[finding.finding_id],
                        confidence=0.65,
                    )
                )
        if gross_margin is not None and op_margin is not None and gross_margin - op_margin > 0.35:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="profitability:adj:capitalize-rd",
                    action="capitalize_rd",
                    priority="low",
                    rationale_code="LARGE_GROSS_TO_OPERATING_GAP",
                    target="income_statement",
                    current_value=op_margin,
                    confidence=0.55,
                    metadata={"gross_margin": gross_margin, "operating_margin": op_margin},
                )
            )
        return adjustments


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
