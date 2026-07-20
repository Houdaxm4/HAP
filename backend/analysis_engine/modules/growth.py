"""Growth analysis module — GROWTH_MODULE_SPEC.md + SCORING_SYSTEM.md.

Consumes only ``CompanyFinancialModel``. Produces a 0–100 Growth Score
with confidence, metrics, findings (GR001–GR032), risks, opportunities,
evidence, and analyst adjustment proposals. No Excel access and no narrative.
"""

from __future__ import annotations

from math import sqrt
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
from analysis_engine.utils import mean, yoy_change
from canonical_model import CompanyFinancialModel, FinancialPoint, FinancialSeries
from rule_library.growth import DEFAULT_INFLATION_RATE, evaluate_growth_rules
from rule_library.growth import GrowthRuleInputs
from scoring_engine.growth import GrowthScoreInputs, score_growth

TREND_WINDOW = 5

_GROWTH_COMPARABLE_CODES = frozenset(
    {
        "REV_CAGR",
        "EPS_CAGR",
        "FCF_CAGR",
        "OI_CAGR",
        "BV_CAGR",
        "REV_YOY",
        "GROWTH_STABILITY",
        "ORGANIC_REV_CAGR",
    }
)

_RISK_BY_RULE: dict[str, str] = {
    "GR005": "LOW_QUALITY_GROWTH",
    "GR006": "SHAREHOLDER_DILUTION",
    "GR007": "ACQUISITION_DRIVEN_GROWTH",
    "GR011": "CASH_CONSUMING_EXPANSION",
    "GR012": "REVENUE_STAGNATION",
    "GR013": "STRUCTURAL_REVENUE_DECLINE",
    "GR015": "LOW_QUALITY_GROWTH",
    "GR017": "SHAREHOLDER_DILUTION",
    "GR020": "UNSTABLE_GROWTH",
    "GR022": "GROWTH_DECELERATION",
    "GR024": "UNSTABLE_GROWTH",
    "GR025": "HYPERGROWTH_FADE_RISK",
    "GR026": "BASE_EFFECT_DISTORTION",
    "GR027": "BASE_EFFECT_DISTORTION",
    "GR028": "BASE_EFFECT_DISTORTION",
    "GR030": "INSUFFICIENT_HISTORY",
    "GR032": "ORGANIC_DECLINE_MASKED",
}

_OPP_BY_RULE: dict[str, str] = {
    "GR001": "EXCEPTIONAL_REVENUE_GROWTH",
    "GR002": "HEALTHY_REVENUE_GROWTH",
    "GR004": "OPERATING_LEVERAGE_IMPROVING",
    "GR008": "EXCEPTIONAL_EARNINGS_GROWTH",
    "GR010": "EXCEPTIONAL_FCF_GROWTH",
    "GR014": "CASH_BACKED_GROWTH",
    "GR016": "ANTI_DILUTIVE_EXPANSION",
    "GR018": "BOOK_VALUE_COMPOUNDING",
    "GR019": "STABLE_GROWTH",
    "GR021": "PERSISTENT_GROWTH",
    "GR023": "GROWTH_ACCELERATION",
    "GR031": "STRONG_ORGANIC_GROWTH",
}


class GrowthModule(AnalysisModule):
    """Evaluate durable growth quality and emit the Growth Score."""

    module_id = "growth"
    module_version = "1.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        revenue_series = model.income_statement.revenue
        if revenue_series.is_empty:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={"revenue": False},
                error="Insufficient growth inputs (need revenue series).",
            )

        metadata = dict(model.metadata or {})
        inflation_rate = float(metadata.get("inflation_rate", DEFAULT_INFLATION_RATE))
        eps_series = model.income_statement.diluted_eps
        fcf_series = model.cash_flow_statement.free_cash_flow
        oi_series = (
            model.income_statement.operating_income
            if not model.income_statement.operating_income.is_empty
            else model.income_statement.ebit
        )
        ni_series = model.income_statement.net_income
        equity_series = model.balance_sheet.shareholders_equity

        period = revenue_series.latest().period if revenue_series.latest() else None
        revenue_points = revenue_series.window_points(TREND_WINDOW)
        revenue_point_count = len(revenue_series.points)
        window_revenue_count = len(revenue_points)

        rev_cagr = revenue_series.cagr(TREND_WINDOW)
        eps_cagr = (
            _economic_cagr(eps_series, TREND_WINDOW) if not eps_series.is_empty else None
        )
        fcf_cagr = (
            _economic_cagr(fcf_series, TREND_WINDOW) if not fcf_series.is_empty else None
        )
        oi_cagr = oi_series.cagr(TREND_WINDOW) if not oi_series.is_empty else None
        ni_cagr = ni_series.cagr(TREND_WINDOW) if not ni_series.is_empty else None

        equity_window = equity_series.window_points(TREND_WINDOW)
        equity_nonpositive = any(point.value <= 0 for point in equity_window)
        bv_cagr = None if equity_nonpositive else equity_series.cagr(TREND_WINDOW)

        rev_yoy_by_period = _yoy_by_period(revenue_series, TREND_WINDOW)
        rev_yoy = rev_yoy_by_period.get(period) if period else None
        if rev_yoy is None and revenue_series.latest() and len(revenue_points) >= 2:
            rev_yoy = yoy_change(revenue_points[-1].value, revenue_points[-2].value)

        eps_yoy = _latest_yoy(eps_series, TREND_WINDOW)
        oi_yoy = _latest_yoy(oi_series, TREND_WINDOW)
        fcf_yoy = _latest_yoy(fcf_series, TREND_WINDOW)

        yoy_values = list(rev_yoy_by_period.values())
        growth_volatility = _coefficient_of_variation(yoy_values)
        growth_stability = (
            1.0 / (1.0 + growth_volatility)
            if growth_volatility is not None and len(yoy_values) >= 3
            else None
        )
        growth_persistence = (
            sum(1 for value in yoy_values if value > 0) / len(yoy_values) if yoy_values else None
        )
        growth_acceleration = _growth_acceleration(revenue_series, TREND_WINDOW)
        growth_trend = _growth_trend(rev_cagr, yoy_values)

        share_series = _series_from_metadata(
            metadata.get("share_count_series"),
            name="Share Count",
            currency="shares",
        )
        share_count_cagr = share_series.cagr(TREND_WINDOW) if not share_series.is_empty else None
        share_count_yoy = _latest_yoy(share_series, TREND_WINDOW)

        rev_per_share_cagr = None
        fcf_per_share_cagr = None
        if not share_series.is_empty:
            rev_ps = _per_share_series(revenue_series, share_series, name="Revenue per Share")
            fcf_ps = _per_share_series(fcf_series, share_series, name="FCF per Share")
            rev_per_share_cagr = rev_ps.cagr(TREND_WINDOW) if not rev_ps.is_empty else None
            fcf_per_share_cagr = fcf_ps.cagr(TREND_WINDOW) if not fcf_ps.is_empty else None

        organic_series, inorganic_share, organic_data_available = _resolve_organic(
            revenue_series, metadata
        )
        organic_rev_cagr = (
            organic_series.cagr(TREND_WINDOW) if organic_series is not None else None
        )

        latest_fcf = fcf_series.latest().value if fcf_series.latest() else None
        eps_point_count = len(eps_series.points)
        fcf_point_count = len(fcf_series.points)

        metrics: list[MetricResult] = []
        evidence_bag: list[Evidence] = []
        evidence_by_metric: dict[str, list[Evidence]] = {}

        metric_defs: list[tuple[str, str, float | None, str]] = [
            ("Revenue CAGR", "REV_CAGR", rev_cagr, "ratio"),
            ("Revenue YoY Growth", "REV_YOY", rev_yoy, "ratio"),
            ("EPS CAGR", "EPS_CAGR", eps_cagr, "ratio"),
            ("EPS Growth (YoY)", "EPS_YOY", eps_yoy, "ratio"),
            ("Operating Income CAGR", "OI_CAGR", oi_cagr, "ratio"),
            ("Operating Income YoY", "OI_YOY", oi_yoy, "ratio"),
            ("FCF CAGR", "FCF_CAGR", fcf_cagr, "ratio"),
            ("FCF YoY Growth", "FCF_YOY", fcf_yoy, "ratio"),
            ("Book Value CAGR", "BV_CAGR", bv_cagr, "ratio"),
            ("Net Income CAGR", "NI_CAGR", ni_cagr, "ratio"),
            ("Organic Revenue CAGR", "ORGANIC_REV_CAGR", organic_rev_cagr, "ratio"),
            ("Inorganic Revenue Share", "INORGANIC_REV_SHARE", inorganic_share, "ratio"),
            ("Share Count CAGR", "SHARE_COUNT_CAGR", share_count_cagr, "ratio"),
            ("Share Count YoY", "SHARE_COUNT_YOY", share_count_yoy, "ratio"),
            ("Revenue per Share CAGR", "REV_PER_SHARE_CAGR", rev_per_share_cagr, "ratio"),
            ("FCF per Share CAGR", "FCF_PER_SHARE_CAGR", fcf_per_share_cagr, "ratio"),
            ("Growth Stability", "GROWTH_STABILITY", growth_stability, "score"),
            ("Growth Volatility", "GROWTH_VOLATILITY", growth_volatility, "score"),
            ("Growth Persistence", "GROWTH_PERSISTENCE", growth_persistence, "ratio"),
            ("Growth Trend Direction", "GROWTH_TREND", growth_trend, "direction"),
            ("Growth Acceleration", "GROWTH_ACCELERATION", growth_acceleration, "ratio"),
            (
                "EPS vs Revenue Growth Spread",
                "EPS_VS_REV_SPREAD",
                (eps_cagr - rev_cagr) if eps_cagr is not None and rev_cagr is not None else None,
                "ratio",
            ),
            (
                "FCF vs Revenue Growth Spread",
                "FCF_VS_REV_SPREAD",
                (fcf_cagr - rev_cagr) if fcf_cagr is not None and rev_cagr is not None else None,
                "ratio",
            ),
            (
                "Op. Income vs Revenue Spread",
                "OI_VS_REV_SPREAD",
                (oi_cagr - rev_cagr) if oi_cagr is not None and rev_cagr is not None else None,
                "ratio",
            ),
            ("Revenue History Length", "REV_HISTORY_YEARS", float(revenue_point_count), "count"),
            ("EPS History Length", "EPS_HISTORY_YEARS", float(eps_point_count), "count"),
            ("FCF History Length", "FCF_HISTORY_YEARS", float(fcf_point_count), "count"),
            (
                "Organic Data Flag",
                "ORGANIC_DATA_AVAILABLE",
                1.0 if organic_data_available else 0.0,
                "flag",
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

        # Also attach source revenue / FCF / EPS facts when available.
        for series, label in [
            (revenue_series, "Revenue"),
            (eps_series, "Diluted EPS"),
            (fcf_series, "Free Cash Flow"),
        ]:
            latest = series.latest()
            if latest is None:
                continue
            evidence_bag.append(
                Evidence(
                    kind="financial_fact",
                    label=label,
                    metric=label.upper().replace(" ", "_"),
                    period=latest.period,
                    value=latest.value,
                    unit=latest.currency,
                    source=latest.source,
                    confidence=latest.confidence,
                )
            )

        confidence_penalty = 0.0
        if window_revenue_count < 5:
            confidence_penalty += 0.08
        if revenue_point_count < 3:
            confidence_penalty += 0.12
        if growth_volatility is not None and growth_volatility > 0.80:
            confidence_penalty += 0.06
        if metadata.get("normalize_covid") or metadata.get("discontinued_operations_impact"):
            confidence_penalty += 0.05

        score_evidence = {
            "REVENUE_CAGR": evidence_by_metric.get("REV_CAGR", []),
            "EPS_CAGR": evidence_by_metric.get("EPS_CAGR", []),
            "FCF_CAGR": evidence_by_metric.get("FCF_CAGR", []),
            "GROWTH_STABILITY": evidence_by_metric.get("GROWTH_STABILITY", []),
            "ORGANIC_GROWTH": evidence_by_metric.get(
                "ORGANIC_REV_CAGR", evidence_by_metric.get("REV_CAGR", [])
            ),
        }
        score_result = score_growth(
            GrowthScoreInputs(
                revenue_cagr=rev_cagr,
                eps_cagr=eps_cagr,
                fcf_cagr=fcf_cagr,
                growth_stability=growth_stability,
                organic_cagr=organic_rev_cagr if organic_data_available else None,
                inorganic_rev_share=inorganic_share,
                latest_fcf=latest_fcf,
                organic_data_available=organic_data_available,
                period=period,
                evidence=score_evidence,
                input_confidence={
                    "REVENUE_CAGR": 0.9,
                    "EPS_CAGR": 0.85,
                    "FCF_CAGR": 0.85,
                    "GROWTH_STABILITY": 0.8,
                    "ORGANIC_GROWTH": 0.9 if organic_data_available else 0.65,
                },
                confidence_penalty=confidence_penalty,
            )
        )

        rule_hits = evaluate_growth_rules(
            GrowthRuleInputs(
                rev_cagr=rev_cagr,
                eps_cagr=eps_cagr,
                fcf_cagr=fcf_cagr,
                oi_cagr=oi_cagr,
                bv_cagr=bv_cagr,
                organic_rev_cagr=organic_rev_cagr if organic_data_available else None,
                inorganic_rev_share=inorganic_share,
                share_count_cagr=share_count_cagr,
                rev_per_share_cagr=rev_per_share_cagr,
                growth_stability=growth_stability,
                growth_volatility=growth_volatility,
                growth_persistence=growth_persistence,
                growth_acceleration=growth_acceleration,
                rev_yoy=rev_yoy,
                rev_yoy_by_period=rev_yoy_by_period,
                latest_fcf=latest_fcf,
                revenue_point_count=revenue_point_count,
                eps_point_count=eps_point_count,
                equity_nonpositive_in_window=equity_nonpositive,
                organic_data_available=organic_data_available,
                inflation_rate=inflation_rate,
                metadata=metadata,
                period=period,
                periods=revenue_series.periods()[-TREND_WINDOW:],
                evidence_by_metric=evidence_by_metric,
            )
        )
        findings = [hit.to_finding() for hit in rule_hits]
        for finding in findings:
            evidence_bag.extend(finding.evidence)

        risks, opportunities = self._risks_and_opportunities(findings)
        adjustments = self._adjustment_proposals(findings, organic_data_available, revenue_point_count)

        if score_result.score is None and not metrics:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                error="Could not compute growth metrics or score.",
            )

        coverage = {
            "revenue": True,
            "eps": not eps_series.is_empty,
            "fcf": not fcf_series.is_empty,
            "revenue_history_years": revenue_point_count,
            "eps_history_years": eps_point_count,
            "fcf_history_years": fcf_point_count,
            "organic_data_available": organic_data_available,
            "effective_weights": score_result.effective_weights,
            "periods_used": revenue_series.periods()[-TREND_WINDOW:],
            "inflation_rate": inflation_rate,
        }
        comparable_metrics = [
            metric for metric in metrics if metric.code in _GROWTH_COMPARABLE_CODES
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
        organic_data_available: bool,
        revenue_point_count: int,
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
                    adjustment_id=f"growth:adj:{action}:{rule_id.lower()}",
                    action=action,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale_code=rationale,
                    target=target,
                    related_finding_ids=[finding_ids[rule_id]],
                    confidence=0.75,
                )
            )

        _add("GR007", "normalize_acquisition_growth", "ACQUISITION_DRIVEN_GROWTH", "metadata.organic_revenue_series")
        _add("GR007", "separate_organic_growth", "ACQUISITION_DRIVEN_GROWTH", "metadata.organic_revenue_series")
        _add("GR032", "normalize_acquisition_growth", "ORGANIC_DECLINE_MASKED", "metadata.organic_revenue_series", "high")
        _add("GR032", "separate_organic_growth", "ORGANIC_DECLINE_MASKED", "metadata.organic_revenue_series", "high")
        _add("GR027", "remove_one_time_revenue", "ONE_TIME_REVENUE_SPIKE", "income_statement.revenue")
        _add("GR026", "normalize_covid_effects", "BASE_EFFECT_DISTORTION", "income_statement.revenue")
        _add(
            "GR028",
            "adjust_discontinued_operations",
            "DISCONTINUED_OPERATIONS",
            "income_statement.revenue",
        )
        _add("GR006", "normalize_share_count", "SHAREHOLDER_DILUTION", "metadata.share_count_series")
        _add("GR017", "use_per_share_growth", "PER_SHARE_EROSION", "derived.rev_per_share")
        _add("GR025", "exclude_hypergrowth_base_year", "HYPERGROWTH_FADE_RISK", "cagr_window")

        if revenue_point_count < 5 or "GR030" in finding_ids:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="growth:adj:request-more-history",
                    action="request_more_data",
                    priority="high" if revenue_point_count < 3 else "medium",
                    rationale_code="INSUFFICIENT_HISTORY",
                    target="income_statement.revenue",
                    related_finding_ids=[finding_ids["GR030"]] if "GR030" in finding_ids else [],
                    confidence=0.9,
                )
            )
        if not organic_data_available and "GR007" not in finding_ids:
            # Soft prompt when acquisition context is unknown.
            pass
        return adjustments


def _economic_cagr(series: FinancialSeries, window: int) -> float | None:
    """CAGR with economically signed negative-to-negative paths.

    Deepening losses (more negative) score as negative growth; shrinking losses
    score as positive growth. Sign changes remain undefined.
    """
    points = series.window_points(window)
    if len(points) < 2:
        return None
    start = points[0].value
    end = points[-1].value
    years = len(points) - 1
    if start == 0 or years <= 0:
        return None
    if start > 0 and end > 0:
        return (end / start) ** (1 / years) - 1
    if start < 0 and end < 0:
        # Less negative ⇒ growth: invert the abs-ratio used by FinancialSeries.cagr.
        return (abs(start) / abs(end)) ** (1 / years) - 1
    return None


def _yoy_by_period(series: FinancialSeries, window: int) -> dict[str, float]:
    points = series.window_points(window)
    result: dict[str, float] = {}
    for index in range(1, len(points)):
        prior = points[index - 1]
        current = points[index]
        change = yoy_change(current.value, prior.value)
        if change is not None and current.period:
            result[current.period] = change
    return result


def _latest_yoy(series: FinancialSeries, window: int) -> float | None:
    if series.is_empty:
        return None
    rates = _yoy_by_period(series, window)
    latest = series.latest()
    if latest is None:
        return None
    return rates.get(latest.period)


def _coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    if avg == 0:
        variance = sum(value * value for value in values) / len(values)
        return sqrt(variance) if variance > 0 else 0.0
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return sqrt(variance) / abs(avg)


def _growth_acceleration(series: FinancialSeries, window: int) -> float | None:
    """Latest 2Y CAGR minus prior 2Y CAGR (three points each)."""
    points = series.window_points(max(window, 5))
    if len(points) < 5:
        return None
    recent = FinancialSeries(name="recent", points=points[-3:])
    prior = FinancialSeries(name="prior", points=points[-5:-2])
    recent_cagr = recent.cagr(window=None)
    prior_cagr = prior.cagr(window=None)
    if recent_cagr is None or prior_cagr is None:
        return None
    return recent_cagr - prior_cagr


def _growth_trend(rev_cagr: float | None, yoy_values: list[float]) -> float | None:
    if rev_cagr is not None:
        if rev_cagr > 0.02:
            return 1.0
        if rev_cagr < -0.02:
            return -1.0
        return 0.0
    if len(yoy_values) < 2:
        return None
    positives = sum(1 for value in yoy_values if value > 0)
    negatives = sum(1 for value in yoy_values if value < 0)
    if positives > negatives:
        return 1.0
    if negatives > positives:
        return -1.0
    return 0.0


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
                        value=float(value),
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
                        value=float(value),
                        currency=currency,
                        source="metadata",
                        confidence=float(item.get("confidence") or 0.8),
                    )
                )
            except (TypeError, ValueError):
                continue
    return series


def _per_share_series(
    numerator: FinancialSeries,
    shares: FinancialSeries,
    *,
    name: str,
) -> FinancialSeries:
    series = FinancialSeries(name=name, currency="ratio")
    for period in shares.periods():
        num = numerator.point_for(period)
        den = shares.point_for(period)
        if num is None or den is None or den.value == 0:
            continue
        series.upsert(
            FinancialPoint(
                period=period,
                value=num.value / den.value,
                currency="ratio",
                source="derived",
                confidence=mean(
                    [c for c in (num.confidence, den.confidence) if c is not None]
                ),
            )
        )
    return series


def _resolve_organic(
    revenue_series: FinancialSeries,
    metadata: dict[str, Any],
) -> tuple[FinancialSeries | None, float | None, bool]:
    organic_raw = metadata.get("organic_revenue_series")
    if organic_raw is not None:
        organic = _series_from_metadata(organic_raw, name="Organic Revenue", currency=revenue_series.currency)
        if not organic.is_empty:
            inorganic = _inorganic_share_from_organic(revenue_series, organic)
            return organic, inorganic, True

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
            organic_value = point.value - acquired_value
            organic.upsert(
                FinancialPoint(
                    period=point.period,
                    value=organic_value,
                    currency=point.currency,
                    source="derived",
                    confidence=point.confidence,
                )
            )
            if point.value != 0:
                shares.append(max(0.0, acquired_value) / abs(point.value))
        inorganic = mean(shares) if shares else None
        return organic if not organic.is_empty else None, inorganic, True

    return None, None, False


def _inorganic_share_from_organic(
    revenue_series: FinancialSeries,
    organic_series: FinancialSeries,
) -> float | None:
    shares: list[float] = []
    for point in revenue_series.window_points(TREND_WINDOW):
        organic = organic_series.point_for(point.period)
        if organic is None or point.value == 0:
            continue
        inorganic = max(0.0, point.value - organic.value)
        shares.append(inorganic / abs(point.value))
    return mean(shares) if shares else None


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
