"""Capital Allocation analysis module — FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM.

Evaluates management capital allocation quality: reinvestment returns, acquisition
economics, buyback discipline, dividend sustainability, and prudent leverage.
Consumes only ``CompanyFinancialModel``.
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
from analysis_engine.utils import mean, paired_periods, safe_div
from canonical_model import CompanyFinancialModel, FinancialPoint, FinancialSeries
from rule_library.capital_allocation import (
    CapitalAllocationRuleInputs,
    evaluate_capital_allocation_rules,
)
from scoring_engine.capital_allocation import (
    CapitalAllocationScoreInputs,
    score_capital_allocation,
)

TREND_WINDOW = 5

_CAPITAL_ALLOCATION_COMPARABLE_CODES = frozenset(
    {
        "ROIC",
        "ROIC_CHANGE",
        "ROIC_SPREAD",
        "REINVESTMENT_RATE",
        "SHARE_COUNT_CAGR",
        "BUYBACK_TO_FCF",
        "PAYOUT_TO_FCF",
        "DIVIDEND_CAGR",
        "ACQUISITION_INTENSITY",
        "INORGANIC_REV_SHARE",
        "EPS_CAGR",
    }
)

_RISK_BY_RULE: dict[str, str] = {
    "CA002": "VALUE_DESTRUCTIVE_ACQUISITION",
    "CA005": "AGGRESSIVE_FINANCIAL_ENGINEERING",
    "CA006": "DETERIORATING_REINVESTMENT_RETURNS",
    "CA007": "SHAREHOLDER_DILUTION",
    "CA009": "UNSUSTAINABLE_DIVIDEND",
    "CA011": "VALUE_DESTRUCTIVE_REINVESTMENT",
    "CA012": "EMPIRE_BUILDING",
    "CA015": "HIGH_PAYOUT_RISK",
    "CA017": "ACQUISITION_MASKING_WEAK_CORE",
    "CA019": "LEVERAGE_FUNDED_EXPANSION",
    "CA021": "ECONOMIC_VALUE_DESTRUCTION",
    "CA022": "WEAK_RETAINED_EARNINGS_DEPLOYMENT",
    "CA023": "INSUFFICIENT_ALLOCATION_HISTORY",
    "CA025": "INCOMPLETE_ACQUISITION_DISCLOSURE",
}

_OPP_BY_RULE: dict[str, str] = {
    "CA001": "EXCELLENT_CAPITAL_ALLOCATION",
    "CA003": "SHAREHOLDER_FRIENDLY",
    "CA004": "VALUE_CREATING_BUYBACKS",
    "CA008": "DISCIPLINED_BUYBACKS",
    "CA010": "VALUE_CREATING_REINVESTMENT",
    "CA014": "BALANCED_CAPITAL_RETURN",
    "CA016": "ACCRETIVE_CAPITAL_RETURN",
    "CA018": "PRUDENT_LEVERAGE_USE",
    "CA020": "IMPROVING_ECONOMIC_SPREAD",
    "CA024": "EXEMPLARY_CAPITAL_ALLOCATION",
}


class CapitalAllocationModule(AnalysisModule):
    """Evaluate capital allocation discipline and emit the Capital Allocation Score."""

    module_id = "capital_allocation"
    module_version = "1.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        income = model.income_statement
        bs = model.balance_sheet
        cfs = model.cash_flow_statement
        metadata = dict(model.metadata or {})

        invested = bs.invested_capital
        has_buybacks = not cfs.share_repurchases.is_empty
        has_dividends = not cfs.dividends.is_empty
        has_share_overlay = bool(metadata.get("share_count_series"))
        has_acq_overlay = bool(
            metadata.get("acquisition_spend_by_period")
            or metadata.get("acquired_revenue_by_period")
            or metadata.get("organic_revenue_series")
        )

        if (
            invested.is_empty
            and not has_buybacks
            and not has_dividends
            and not has_share_overlay
            and not has_acq_overlay
            and cfs.free_cash_flow.is_empty
            and cfs.operating_cash_flow.is_empty
        ):
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={"capital_allocation": False},
                error="Insufficient capital allocation inputs.",
            )

        roic_series = _build_roic_series(model)
        fcf_series = _resolve_fcf_series(
            cfs.operating_cash_flow,
            cfs.capital_expenditures,
            cfs.free_cash_flow,
        )
        buyback_series = _abs_series(cfs.share_repurchases)
        dividend_series = _abs_series(cfs.dividends)
        capex_series = _abs_series(cfs.capital_expenditures)
        debt_series = bs.total_debt
        revenue_series = income.revenue
        eps_series = income.diluted_eps

        share_series = _series_from_metadata(
            metadata.get("share_count_series"),
            name="Share Count",
            currency="shares",
        )
        acquisition_series = _series_from_metadata(
            metadata.get("acquisition_spend_by_period"),
            name="Acquisition Spend",
            currency=model.reporting_currency,
        )

        organic_series, inorganic_share, organic_data_available = _resolve_organic(
            revenue_series, metadata
        )
        if inorganic_share is None:
            inorganic_share = _infer_inorganic_share(revenue_series, acquisition_series)

        wacc = model.valuation_inputs.wacc
        assumed_wacc = wacc if wacc is not None else 0.08

        roic_points = roic_series.window_points(TREND_WINDOW)
        latest_roic = roic_series.latest().value if roic_series.latest() else None
        earliest_roic = roic_points[0].value if roic_points else None
        roic_change = (
            latest_roic - earliest_roic
            if latest_roic is not None and earliest_roic is not None
            else None
        )
        roic_spread = (
            latest_roic - assumed_wacc if latest_roic is not None else None
        )
        earliest_spread = (
            earliest_roic - assumed_wacc
            if earliest_roic is not None
            else None
        )
        roic_spread_change = (
            roic_spread - earliest_spread
            if roic_spread is not None and earliest_spread is not None
            else None
        )

        share_count_cagr = (
            share_series.cagr(TREND_WINDOW) if not share_series.is_empty else None
        )
        eps_cagr = eps_series.cagr(TREND_WINDOW) if not eps_series.is_empty else None
        dividend_cagr = (
            dividend_series.cagr(TREND_WINDOW) if not dividend_series.is_empty else None
        )

        latest_fcf = fcf_series.latest().value if fcf_series.latest() else None
        latest_buybacks = buyback_series.latest().value if buyback_series.latest() else None
        latest_dividends = dividend_series.latest().value if dividend_series.latest() else None

        total_buybacks = _sum_window(buyback_series, TREND_WINDOW)
        total_dividends = _sum_window(dividend_series, TREND_WINDOW)
        total_fcf = _sum_window(fcf_series, TREND_WINDOW)

        buyback_to_fcf = (
            safe_div(latest_buybacks, latest_fcf)
            if latest_fcf is not None and latest_fcf > 0 and latest_buybacks is not None
            else safe_div(total_buybacks, total_fcf) if total_fcf and total_fcf > 0 else None
        )
        payout_to_fcf = (
            safe_div(latest_dividends, latest_fcf)
            if latest_fcf is not None and latest_fcf > 0 and latest_dividends is not None
            else safe_div(total_dividends, total_fcf) if total_fcf and total_fcf > 0 else None
        )

        reinvestment_rate = _compute_reinvestment_rate(
            model, capex_series, acquisition_series, TREND_WINDOW
        )
        acquisition_intensity = _compute_acquisition_intensity(
            acquisition_series, revenue_series, TREND_WINDOW
        )
        debt_change = _relative_change(debt_series, TREND_WINDOW)
        organic_rev_cagr = (
            organic_series.cagr(TREND_WINDOW)
            if organic_series is not None and not organic_series.is_empty
            else None
        )

        dividend_by_period = {
            point.period: point.value
            for point in dividend_series.window_points(TREND_WINDOW)
            if point.period
        }

        buybacks_below_intrinsic = bool(metadata.get("buybacks_below_intrinsic"))
        if not buybacks_below_intrinsic:
            intrinsic = metadata.get("intrinsic_value_per_share")
            avg_buyback_price = metadata.get("avg_buyback_price")
            if intrinsic is not None and avg_buyback_price is not None:
                try:
                    buybacks_below_intrinsic = float(avg_buyback_price) < float(intrinsic)
                except (TypeError, ValueError):
                    pass

        period = (
            (roic_series.latest() or fcf_series.latest() or buyback_series.latest()).period
            if (roic_series.latest() or fcf_series.latest() or buyback_series.latest())
            else None
        )
        periods_used = roic_series.periods()[-TREND_WINDOW:] or fcf_series.periods()[-TREND_WINDOW:]

        history_points = max(
            len(roic_series.points),
            len(share_series.points),
            len(fcf_series.points),
            len(dividend_series.points),
            len(buyback_series.points),
        )

        acquisition_data_available = has_acq_overlay or not acquisition_series.is_empty

        confidence_penalty = 0.0
        if invested.is_empty:
            confidence_penalty += 0.12
        if share_series.is_empty and not has_buybacks:
            confidence_penalty += 0.08
        if history_points < 3:
            confidence_penalty += 0.10
        if history_points < 5:
            confidence_penalty += 0.05
        if cfs.free_cash_flow.is_empty and not fcf_series.is_empty:
            confidence_penalty += 0.06
        if wacc is None:
            confidence_penalty += 0.04
        if (
            not acquisition_data_available
            and inorganic_share is not None
            and inorganic_share >= 0.20
        ):
            confidence_penalty += 0.08
        if reinvestment_rate is None:
            confidence_penalty += 0.06

        metrics: list[MetricResult] = []
        evidence_bag: list[Evidence] = []
        evidence_by_metric: dict[str, list[Evidence]] = {}

        metric_defs: list[tuple[str, str, float | None, str]] = [
            ("ROIC", "ROIC", latest_roic, "ratio"),
            ("ROIC Change", "ROIC_CHANGE", roic_change, "ratio"),
            ("ROIC Spread vs WACC", "ROIC_SPREAD", roic_spread, "ratio"),
            ("ROIC Spread Change", "ROIC_SPREAD_CHANGE", roic_spread_change, "ratio"),
            ("Reinvestment Rate", "REINVESTMENT_RATE", reinvestment_rate, "ratio"),
            ("Share Count CAGR", "SHARE_COUNT_CAGR", share_count_cagr, "ratio"),
            ("EPS CAGR", "EPS_CAGR", eps_cagr, "ratio"),
            ("Buyback to FCF", "BUYBACK_TO_FCF", buyback_to_fcf, "ratio"),
            ("Dividend Payout to FCF", "PAYOUT_TO_FCF", payout_to_fcf, "ratio"),
            ("Dividend CAGR", "DIVIDEND_CAGR", dividend_cagr, "ratio"),
            ("Acquisition Intensity", "ACQUISITION_INTENSITY", acquisition_intensity, "ratio"),
            ("Inorganic Revenue Share", "INORGANIC_REV_SHARE", inorganic_share, "ratio"),
            ("Organic Revenue CAGR", "ORGANIC_REV_CAGR", organic_rev_cagr, "ratio"),
            ("Debt Change", "DEBT_CHANGE", debt_change, "ratio"),
            ("Total Buybacks (Window)", "TOTAL_BUYBACKS", total_buybacks, model.reporting_currency),
            ("Total Dividends (Window)", "TOTAL_DIVIDENDS", total_dividends, model.reporting_currency),
            ("Latest FCF", "LATEST_FCF", latest_fcf, model.reporting_currency),
            (
                "CA History Length",
                "CA_HISTORY_YEARS",
                float(history_points),
                "count",
            ),
        ]

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

        score_result = score_capital_allocation(
            CapitalAllocationScoreInputs(
                roic_change=roic_change,
                share_count_cagr=share_count_cagr,
                buyback_to_fcf=buyback_to_fcf,
                payout_to_fcf=payout_to_fcf,
                dividend_cagr=dividend_cagr,
                reinvestment_rate=reinvestment_rate,
                roic=latest_roic,
                wacc=wacc,
                inorganic_share=inorganic_share,
                acquisition_intensity=acquisition_intensity,
                period=period,
                evidence={
                    "ROIC_TREND": evidence_by_metric.get("ROIC_CHANGE", []),
                    "SHARE_BUYBACKS": evidence_by_metric.get("SHARE_COUNT_CAGR", []),
                    "DIVIDEND_POLICY": evidence_by_metric.get("PAYOUT_TO_FCF", []),
                    "REINVESTMENT_QUALITY": evidence_by_metric.get("REINVESTMENT_RATE", []),
                    "ACQUISITION_QUALITY": evidence_by_metric.get("INORGANIC_REV_SHARE", []),
                },
                input_confidence={
                    "ROIC_TREND": 0.85 if not invested.is_empty else 0.55,
                    "SHARE_BUYBACKS": 0.85 if not share_series.is_empty or has_buybacks else 0.6,
                    "DIVIDEND_POLICY": 0.85 if has_dividends else 0.55,
                    "REINVESTMENT_QUALITY": 0.8 if reinvestment_rate is not None else 0.5,
                    "ACQUISITION_QUALITY": 0.8 if acquisition_data_available else 0.55,
                },
                confidence_penalty=confidence_penalty,
            )
        )

        rule_hits = evaluate_capital_allocation_rules(
            CapitalAllocationRuleInputs(
                roic=latest_roic,
                roic_change=roic_change,
                roic_spread=roic_spread,
                roic_spread_change=roic_spread_change,
                share_count_cagr=share_count_cagr,
                eps_cagr=eps_cagr,
                buyback_to_fcf=buyback_to_fcf,
                payout_to_fcf=payout_to_fcf,
                dividend_cagr=dividend_cagr,
                reinvestment_rate=reinvestment_rate,
                inorganic_share=inorganic_share,
                acquisition_intensity=acquisition_intensity,
                debt_change=debt_change,
                organic_rev_cagr=organic_rev_cagr,
                latest_fcf=latest_fcf,
                total_dividends=total_dividends,
                total_buybacks=total_buybacks,
                buybacks_below_intrinsic=buybacks_below_intrinsic,
                organic_data_available=organic_data_available,
                acquisition_data_available=acquisition_data_available,
                history_points=history_points,
                period=period,
                periods=periods_used,
                dividend_by_period=dividend_by_period,
                evidence_by_metric=evidence_by_metric,
            )
        )
        findings = [hit.to_finding() for hit in rule_hits]
        for finding in findings:
            evidence_bag.extend(finding.evidence)

        risks, opportunities = self._risks_and_opportunities(findings)
        adjustments = self._adjustment_proposals(
            findings,
            metadata=metadata,
            invested_available=not invested.is_empty,
            share_overlay=has_share_overlay,
            acquisition_data_available=acquisition_data_available,
            history_points=history_points,
        )

        if score_result.score is None and not metrics:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                error="Could not compute capital allocation metrics or score.",
            )

        coverage = {
            "invested_capital": not invested.is_empty,
            "share_repurchases": has_buybacks,
            "dividends": has_dividends,
            "share_count_overlay": has_share_overlay,
            "acquisition_overlay": has_acq_overlay,
            "organic_data_available": organic_data_available,
            "fcf_derived": cfs.free_cash_flow.is_empty and not fcf_series.is_empty,
            "wacc_assumed": wacc is None,
            "ca_history_years": history_points,
            "effective_weights": score_result.effective_weights,
            "periods_used": periods_used,
        }
        comparable = [m for m in metrics if m.code in _CAPITAL_ALLOCATION_COMPARABLE_CODES]
        coverage = attach_metric_comparisons(
            coverage,
            self.build_metric_comparisons(model, comparable, period=period),
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
        *,
        metadata: dict[str, Any],
        invested_available: bool,
        share_overlay: bool,
        acquisition_data_available: bool,
        history_points: int,
    ) -> list[AnalystAdjustmentProposal]:
        adjustments: list[AnalystAdjustmentProposal] = []
        finding_ids = {f.rule_id: f.finding_id for f in findings}

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
                    adjustment_id=f"capital_allocation:adj:{action}:{rule_id.lower()}",
                    action=action,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale_code=rationale,
                    target=target,
                    related_finding_ids=[finding_ids[rule_id]],
                    confidence=0.75,
                )
            )

        _add("CA002", "review_assumption", "ACQUISITION_RETURNS", "metadata.acquisition_spend_by_period", "high")
        _add("CA005", "review_assumption", "DEBT_FUNDED_BUYBACKS", "cash_flow_statement.share_repurchases", "high")
        _add("CA009", "review_assumption", "UNSUSTAINABLE_DIVIDEND", "cash_flow_statement.dividends", "high")
        _add("CA011", "review_assumption", "REINVESTMENT_HURDLE", "balance_sheet.invested_capital", "high")
        _add("CA012", "normalize_acquisition_growth", "EMPIRE_BUILDING", "metadata.organic_revenue_series", "high")
        _add("CA017", "separate_organic_growth", "ORGANIC_DECLINE_MASKED", "metadata.organic_revenue_series", "high")
        _add("CA021", "review_assumption", "ROIC_BELOW_WACC", "balance_sheet.invested_capital", "high")
        _add("CA007", "normalize_share_count", "SHAREHOLDER_DILUTION", "metadata.share_count_series")
        _add("CA025", "request_more_data", "MISSING_ACQUISITION_DISCLOSURE", "metadata.acquisition_spend_by_period")

        if not invested_available:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="capital_allocation:adj:request-invested-capital",
                    action="request_more_data",
                    priority="high",
                    rationale_code="NEED_INVESTED_CAPITAL_FOR_ROIC",
                    target="balance_sheet.invested_capital",
                    confidence=0.9,
                )
            )
        if not share_overlay and "CA007" not in finding_ids:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="capital_allocation:adj:request-share-count",
                    action="request_more_data",
                    priority="medium",
                    rationale_code="MISSING_SHARE_COUNT",
                    target="metadata.share_count_series",
                    confidence=0.8,
                )
            )
        if not acquisition_data_available:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="capital_allocation:adj:request-acquisition-data",
                    action="request_more_data",
                    priority="medium",
                    rationale_code="MISSING_ACQUISITION_DISCLOSURE",
                    target="metadata.acquisition_spend_by_period",
                    confidence=0.75,
                )
            )
        if history_points < 5:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="capital_allocation:adj:request-history",
                    action="request_more_data",
                    priority="medium",
                    rationale_code="INSUFFICIENT_ALLOCATION_HISTORY",
                    target="balance_sheet.invested_capital",
                    related_finding_ids=[finding_ids["CA023"]] if "CA023" in finding_ids else [],
                    confidence=0.85,
                )
            )
        if metadata.get("off_balance_sheet_obligations"):
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="capital_allocation:adj:off-balance-sheet",
                    action="review_assumption",
                    priority="medium",
                    rationale_code="OFF_BALANCE_SHEET",
                    target="metadata.off_balance_sheet_obligations",
                    confidence=0.7,
                )
            )
        return adjustments


def _build_roic_series(model: CompanyFinancialModel) -> FinancialSeries:
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


def _resolve_fcf_series(
    ocf: FinancialSeries,
    capex: FinancialSeries,
    reported_fcf: FinancialSeries,
) -> FinancialSeries:
    if not reported_fcf.is_empty:
        return reported_fcf
    derived = FinancialSeries(name="Free Cash Flow", currency=ocf.currency or reported_fcf.currency)
    for period in paired_periods(ocf, capex):
        ocf_point = ocf.point_for(period)
        capex_point = capex.point_for(period)
        if ocf_point is None or capex_point is None:
            continue
        derived.upsert(
            FinancialPoint(
                period=period,
                value=ocf_point.value - abs(capex_point.value),
                currency=ocf_point.currency,
                source="derived",
                confidence=mean(
                    [c for c in (ocf_point.confidence, capex_point.confidence) if c is not None]
                ),
                audited=bool(ocf_point.audited and capex_point.audited),
            )
        )
    return derived


def _compute_reinvestment_rate(
    model: CompanyFinancialModel,
    capex_series: FinancialSeries,
    acquisition_series: FinancialSeries,
    window: int,
) -> float | None:
    income = model.income_statement
    ebit_series = income.ebit if not income.ebit.is_empty else income.operating_income
    tax_series = income.tax_expense
    assumed_tax = model.valuation_inputs.tax_rate
    after_tax_default = 1.0 - assumed_tax if assumed_tax is not None else 0.75

    rates: list[float] = []
    for period in ebit_series.periods()[-window:]:
        ebit = ebit_series.point_for(period)
        if ebit is None or ebit.value == 0:
            continue
        tax = tax_series.point_for(period)
        if tax is not None and ebit.value != 0:
            tax_rate = max(0.0, min(0.5, abs(tax.value) / abs(ebit.value)))
            nopat = ebit.value * (1.0 - tax_rate)
        else:
            nopat = ebit.value * after_tax_default
        if nopat <= 0:
            continue
        capex_point = capex_series.point_for(period)
        acq_point = acquisition_series.point_for(period)
        reinvestment = (capex_point.value if capex_point else 0.0) + (
            acq_point.value if acq_point else 0.0
        )
        rate = reinvestment / nopat
        if rate >= 0:
            rates.append(rate)
    return mean(rates) if rates else None


def _compute_acquisition_intensity(
    acquisition_series: FinancialSeries,
    revenue_series: FinancialSeries,
    window: int,
) -> float | None:
    if acquisition_series.is_empty or revenue_series.is_empty:
        return None
    acq_total = _sum_window(acquisition_series, window)
    rev_total = _sum_window(revenue_series, window)
    return safe_div(acq_total, rev_total)


def _relative_change(series: FinancialSeries, window: int) -> float | None:
    points = series.window_points(window)
    if len(points) < 2:
        return None
    first, last = points[0].value, points[-1].value
    if first == 0:
        return None
    return (last - first) / abs(first)


def _sum_window(series: FinancialSeries, window: int) -> float | None:
    points = series.window_points(window)
    if not points:
        return None
    return sum(point.value for point in points)


def _infer_inorganic_share(
    revenue_series: FinancialSeries,
    acquisition_series: FinancialSeries,
) -> float | None:
    if not acquisition_series.is_empty:
        return _compute_acquisition_intensity(acquisition_series, revenue_series, TREND_WINDOW)
    points = revenue_series.window_points(TREND_WINDOW)
    if len(points) < 3:
        return None
    step_ups = 0
    for idx in range(1, len(points)):
        prior = points[idx - 1].value
        current = points[idx].value
        if prior > 0 and (current - prior) / prior > 0.25:
            step_ups += 1
    if step_ups >= 2:
        return min(0.5, 0.15 * step_ups)
    return None


def _resolve_organic(
    revenue_series: FinancialSeries,
    metadata: dict[str, Any],
) -> tuple[FinancialSeries | None, float | None, bool]:
    organic_raw = metadata.get("organic_revenue_series")
    if organic_raw is not None:
        organic = _series_from_metadata(
            organic_raw, name="Organic Revenue", currency=revenue_series.currency
        )
        if not organic.is_empty:
            shares: list[float] = []
            for point in revenue_series.window_points(TREND_WINDOW):
                organic_point = organic.point_for(point.period)
                if organic_point is None or point.value == 0:
                    continue
                shares.append(max(0.0, 1.0 - organic_point.value / point.value))
            return organic, mean(shares), True

    acquired_raw = metadata.get("acquired_revenue_by_period")
    if acquired_raw is not None:
        acquired = _series_from_metadata(
            acquired_raw, name="Acquired Revenue", currency=revenue_series.currency
        )
        organic = FinancialSeries(name="Organic Revenue", currency=revenue_series.currency)
        shares: list[float] = []
        for point in revenue_series.window_points(TREND_WINDOW):
            acquired_point = acquired.point_for(point.period)
            acquired_value = acquired_point.value if acquired_point else 0.0
            organic.upsert(
                FinancialPoint(
                    period=point.period,
                    value=point.value - acquired_value,
                    currency=point.currency,
                    source="derived",
                    confidence=point.confidence,
                )
            )
            if point.value != 0:
                shares.append(max(0.0, acquired_value) / abs(point.value))
        return organic if not organic.is_empty else None, mean(shares), True

    return None, None, False


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
