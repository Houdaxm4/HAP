"""Balance Sheet analysis module — FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM.

Consumes only ``CompanyFinancialModel``. Produces a 0–100 Balance Sheet Score
with HAP metrics, findings (BS001+), risks, opportunities, workbook comparisons,
and analyst adjustment proposals.
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
from rule_library.balance_sheet import BalanceSheetRuleInputs, evaluate_balance_sheet_rules
from scoring_engine.balance_sheet import BalanceSheetScoreInputs, score_balance_sheet

TREND_WINDOW = 5

_BALANCE_SHEET_COMPARABLE_CODES = frozenset(
    {
        "CURRENT_RATIO",
        "QUICK_RATIO",
        "CASH_RATIO",
        "DEBT_TO_EQUITY",
        "DEBT_TO_EBITDA",
        "NET_DEBT",
        "NET_DEBT_TO_EBITDA",
        "INTEREST_COVERAGE",
        "CASH_TO_DEBT",
        "WORKING_CAPITAL",
    }
)

_RISK_BY_RULE: dict[str, str] = {
    "BS002": "LIQUIDITY_WEAKNESS",
    "BS003": "EXCESSIVE_LEVERAGE",
    "BS004": "DEBT_SERVICING_RISK",
    "BS008": "LIQUIDITY_WEAKNESS",
    "BS010": "LIQUIDITY_WEAKNESS",
    "BS011": "HIGH_LEVERAGE",
    "BS013": "EXCESSIVE_LEVERAGE",
    "BS016": "REFINANCING_RISK",
    "BS018": "DEBT_SERVICING_RISK",
    "BS019": "INCOMPLETE_COVERAGE_DATA",
    "BS020": "WORKING_CAPITAL_DEFICIT",
    "BS022": "WORKING_CAPITAL_DETERIORATION",
    "BS023": "RISING_DEBT_LOAD",
    "BS025": "LIQUIDITY_WEAKNESS",
    "BS027": "INCREASING_LEVERAGE",
    "BS028": "LIABILITY_GROWTH_RISK",
    "BS030": "INSUFFICIENT_HISTORY",
    "BS031": "OFF_BALANCE_SHEET_RISK",
}

_OPP_BY_RULE: dict[str, str] = {
    "BS001": "STRONG_LIQUIDITY",
    "BS005": "NET_CASH_POSITION",
    "BS006": "BALANCE_SHEET_STRENGTHENING",
    "BS007": "STRONG_QUICK_LIQUIDITY",
    "BS009": "HIGH_CASH_LIQUIDITY",
    "BS012": "CONSERVATIVE_LEVERAGE",
    "BS014": "MODEST_NET_LEVERAGE",
    "BS015": "STRONG_CASH_VS_DEBT",
    "BS017": "EXCEPTIONAL_INTEREST_COVERAGE",
    "BS021": "WORKING_CAPITAL_IMPROVING",
    "BS024": "IMPROVING_LIQUIDITY",
    "BS026": "DELEVERAGING_TREND",
    "BS029": "FORTRESS_BALANCE_SHEET",
}


class BalanceSheetModule(AnalysisModule):
    """Evaluate financial strength and emit the Balance Sheet Score."""

    module_id = "balance_sheet"
    module_version = "1.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        bs = model.balance_sheet
        income = model.income_statement
        metadata = dict(model.metadata or {})

        if (
            bs.current_assets.is_empty
            and bs.cash.is_empty
            and bs.total_debt.is_empty
            and bs.current_liabilities.is_empty
        ):
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={"balance_sheet": False},
                error="Insufficient balance sheet inputs.",
            )

        ca_series = bs.current_assets
        cl_series = bs.current_liabilities
        cash_series = bs.cash
        debt_series = bs.total_debt
        equity_series = bs.shareholders_equity

        quick_assets_series = _build_quick_assets_series(bs, metadata)
        working_capital_series = _build_working_capital_series(ca_series, cl_series)
        ebitda_series = _ebitda_series(income)
        ebit_series = (
            income.ebit if not income.ebit.is_empty else income.operating_income
        )
        interest_series = income.interest_expense

        current_ratio_series = ratio_series(
            name="Current Ratio",
            numerator=ca_series,
            denominator=cl_series,
            currency="ratio",
        )
        quick_ratio_series = ratio_series(
            name="Quick Ratio",
            numerator=quick_assets_series,
            denominator=cl_series,
            currency="ratio",
        )
        cash_ratio_series = ratio_series(
            name="Cash Ratio",
            numerator=cash_series,
            denominator=cl_series,
            currency="ratio",
        )
        debt_to_equity_series = ratio_series(
            name="Debt to Equity",
            numerator=debt_series,
            denominator=equity_series,
            currency="ratio",
        )
        debt_to_ebitda_series = ratio_series(
            name="Debt to EBITDA",
            numerator=debt_series,
            denominator=ebitda_series,
            currency="ratio",
        )
        interest_coverage_series = ratio_series(
            name="Interest Coverage",
            numerator=ebit_series,
            denominator=_abs_series(interest_series),
            currency="ratio",
        )

        period = (
            (ca_series.latest() or cash_series.latest() or debt_series.latest()).period
            if (ca_series.latest() or cash_series.latest() or debt_series.latest())
            else None
        )

        latest_ca = ca_series.latest().value if ca_series.latest() else None
        latest_cl = cl_series.latest().value if cl_series.latest() else None
        latest_cash = cash_series.latest().value if cash_series.latest() else None
        latest_debt = debt_series.latest().value if debt_series.latest() else None
        latest_equity = equity_series.latest().value if equity_series.latest() else None
        latest_ebitda = ebitda_series.latest().value if ebitda_series.latest() else None

        net_debt = _resolve_net_debt(model, latest_debt, latest_cash)
        working_capital = (
            working_capital_series.latest().value if working_capital_series.latest() else None
        )
        if working_capital is None and latest_ca is not None and latest_cl is not None:
            working_capital = latest_ca - latest_cl

        current_ratio = (
            current_ratio_series.latest().value if current_ratio_series.latest() else None
        )
        if current_ratio is None:
            current_ratio = safe_div(latest_ca, latest_cl)

        quick_ratio = quick_ratio_series.latest().value if quick_ratio_series.latest() else None
        cash_ratio = cash_ratio_series.latest().value if cash_ratio_series.latest() else None
        debt_to_equity = (
            debt_to_equity_series.latest().value if debt_to_equity_series.latest() else None
        )
        debt_to_ebitda = (
            debt_to_ebitda_series.latest().value if debt_to_ebitda_series.latest() else None
        )
        if debt_to_ebitda is None and latest_debt is not None and latest_ebitda:
            debt_to_ebitda = safe_div(latest_debt, latest_ebitda)

        interest_coverage = (
            interest_coverage_series.latest().value
            if interest_coverage_series.latest()
            else None
        )
        net_debt_to_ebitda = (
            safe_div(net_debt, latest_ebitda) if net_debt is not None and latest_ebitda else None
        )
        cash_to_debt = safe_div(latest_cash, latest_debt) if latest_debt else None

        debt_cagr = debt_series.cagr(TREND_WINDOW) if len(debt_series) >= 2 else None
        ca_cagr = ca_series.cagr(TREND_WINDOW) if len(ca_series) >= 2 else None
        cl_cagr = cl_series.cagr(TREND_WINDOW) if len(cl_series) >= 2 else None

        liquidity_trend = _trend_score(current_ratio_series)
        leverage_trend = _trend_score(debt_to_equity_series)
        working_capital_trend = _trend_score(working_capital_series)

        bs_point_count = max(
            len(ca_series.points),
            len(cl_series.points),
            len(debt_series.points),
            len(cash_series.points),
        )

        debt_by_period = {
            point.period: point.value
            for point in debt_series.window_points(TREND_WINDOW)
            if point.period
        }
        wc_by_period = {
            point.period: point.value
            for point in working_capital_series.window_points(TREND_WINDOW)
            if point.period
        }

        interest_available = not interest_series.is_empty and any(
            point.value != 0 for point in interest_series.window_points(TREND_WINDOW)
        )
        material_debt = latest_debt is not None and latest_debt > 0
        ebitda_proxy = income.ebitda.is_empty

        metrics: list[MetricResult] = []
        evidence_bag: list[Evidence] = []
        evidence_by_metric: dict[str, list[Evidence]] = {}

        confidence_penalty = 0.0
        if bs_point_count < 3:
            confidence_penalty += 0.10
        if bs_point_count < 5:
            confidence_penalty += 0.05
        if not interest_available and material_debt:
            confidence_penalty += 0.10
        if ebitda_proxy:
            confidence_penalty += 0.06
        if metadata.get("inventory_series") is None and metadata.get("inventory_by_period") is None:
            confidence_penalty += 0.04
        if debt_to_ebitda is not None and debt_series.is_empty:
            confidence_penalty += 0.05

        metric_defs: list[tuple[str, str, float | None, str]] = [
            ("Current Ratio", "CURRENT_RATIO", current_ratio, "ratio"),
            ("Quick Ratio", "QUICK_RATIO", quick_ratio, "ratio"),
            ("Cash Ratio", "CASH_RATIO", cash_ratio, "ratio"),
            ("Working Capital", "WORKING_CAPITAL", working_capital, model.reporting_currency),
            ("Working Capital Trend", "WORKING_CAPITAL_TREND", working_capital_trend, "direction"),
            ("Debt to Equity", "DEBT_TO_EQUITY", debt_to_equity, "ratio"),
            ("Debt to EBITDA", "DEBT_TO_EBITDA", debt_to_ebitda, "ratio"),
            ("Net Debt", "NET_DEBT", net_debt, model.reporting_currency),
            ("Net Debt to EBITDA", "NET_DEBT_TO_EBITDA", net_debt_to_ebitda, "ratio"),
            ("Interest Coverage", "INTEREST_COVERAGE", interest_coverage, "ratio"),
            ("Cash to Debt", "CASH_TO_DEBT", cash_to_debt, "ratio"),
            ("Debt CAGR", "DEBT_CAGR", debt_cagr, "ratio"),
            ("Current Assets CAGR", "CURRENT_ASSETS_CAGR", ca_cagr, "ratio"),
            ("Current Liabilities CAGR", "CURRENT_LIABILITIES_CAGR", cl_cagr, "ratio"),
            ("Liquidity Trend", "LIQUIDITY_TREND", liquidity_trend, "direction"),
            ("Leverage Trend", "LEVERAGE_TREND", leverage_trend, "direction"),
            ("BS History Length", "BS_HISTORY_YEARS", float(bs_point_count), "count"),
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

        score_result = score_balance_sheet(
            BalanceSheetScoreInputs(
                debt_to_ebitda=debt_to_ebitda,
                current_ratio=current_ratio,
                interest_coverage=interest_coverage,
                net_debt=net_debt,
                ebitda=latest_ebitda,
                working_capital_trend=working_capital_trend,
                period=period,
                evidence={
                    "DEBT": evidence_by_metric.get("DEBT_TO_EBITDA", []),
                    "LIQUIDITY": evidence_by_metric.get("CURRENT_RATIO", []),
                    "INTEREST_COVERAGE": evidence_by_metric.get("INTEREST_COVERAGE", []),
                    "NET_CASH_POSITION": evidence_by_metric.get("NET_DEBT", []),
                    "WORKING_CAPITAL": evidence_by_metric.get("WORKING_CAPITAL_TREND", []),
                },
                input_confidence={
                    "DEBT": 0.85 if not ebitda_proxy else 0.7,
                    "LIQUIDITY": 0.9,
                    "INTEREST_COVERAGE": 0.85 if interest_available else 0.5,
                    "NET_CASH_POSITION": 0.85,
                    "WORKING_CAPITAL": 0.8,
                },
                confidence_penalty=confidence_penalty,
            )
        )

        rule_hits = evaluate_balance_sheet_rules(
            BalanceSheetRuleInputs(
                current_ratio=current_ratio,
                quick_ratio=quick_ratio,
                cash_ratio=cash_ratio,
                debt_to_equity=debt_to_equity,
                debt_to_ebitda=debt_to_ebitda,
                net_debt=net_debt,
                net_debt_to_ebitda=net_debt_to_ebitda,
                interest_coverage=interest_coverage,
                cash_to_debt=cash_to_debt,
                working_capital=working_capital,
                working_capital_by_period=wc_by_period,
                debt_by_period=debt_by_period,
                debt_cagr=debt_cagr,
                current_assets_cagr=ca_cagr,
                current_liabilities_cagr=cl_cagr,
                liquidity_trend=liquidity_trend,
                leverage_trend=leverage_trend,
                working_capital_trend=working_capital_trend,
                interest_expense_available=interest_available,
                material_debt=material_debt,
                balance_sheet_point_count=bs_point_count,
                off_balance_sheet_flag=bool(metadata.get("off_balance_sheet_obligations")),
                period=period,
                periods=ca_series.periods()[-TREND_WINDOW:],
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
            interest_available=interest_available,
            bs_point_count=bs_point_count,
        )

        if score_result.score is None and not metrics:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                error="Could not compute balance sheet metrics or score.",
            )

        coverage = {
            "current_assets": not ca_series.is_empty,
            "current_liabilities": not cl_series.is_empty,
            "total_debt": not debt_series.is_empty,
            "cash": not cash_series.is_empty,
            "interest_expense_available": interest_available,
            "ebitda_proxy_used": ebitda_proxy,
            "bs_history_years": bs_point_count,
            "effective_weights": score_result.effective_weights,
            "periods_used": ca_series.periods()[-TREND_WINDOW:],
        }
        comparable = [m for m in metrics if m.code in _BALANCE_SHEET_COMPARABLE_CODES]
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
        metadata: dict[str, Any],
        interest_available: bool,
        bs_point_count: int,
    ) -> list[AnalystAdjustmentProposal]:
        adjustments: list[AnalystAdjustmentProposal] = []
        finding_ids = {f.rule_id: f.finding_id for f in findings}

        def _add(rule_id: str, action: str, rationale: str, target: str, priority: str = "medium") -> None:
            if rule_id not in finding_ids:
                return
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id=f"balance_sheet:adj:{action}:{rule_id.lower()}",
                    action=action,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale_code=rationale,
                    target=target,
                    related_finding_ids=[finding_ids[rule_id]],
                    confidence=0.75,
                )
            )

        _add("BS003", "review_assumption", "EXCESSIVE_LEVERAGE", "balance_sheet.total_debt", "high")
        _add("BS011", "review_assumption", "DEBT_CLASSIFICATION", "balance_sheet.total_debt")
        _add("BS023", "review_assumption", "DEBT_CLASSIFICATION", "balance_sheet.total_debt")
        _add("BS031", "review_assumption", "OFF_BALANCE_SHEET", "metadata.off_balance_sheet_obligations", "high")
        _add("BS022", "review_assumption", "SEASONAL_WORKING_CAPITAL", "balance_sheet.current_assets")
        _add("BS028", "review_assumption", "SEASONAL_WORKING_CAPITAL", "balance_sheet.current_liabilities")
        _add("BS004", "request_more_data", "DEBT_MATURITY", "metadata.debt_maturity_schedule", "high")
        _add("BS016", "request_more_data", "DEBT_MATURITY", "metadata.debt_maturity_schedule")
        _add("BS019", "request_more_data", "MISSING_INTEREST_EXPENSE", "income_statement.interest_expense", "high")

        if not interest_available:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="balance_sheet:adj:request-interest",
                    action="request_more_data",
                    priority="medium",
                    rationale_code="MISSING_INTEREST_EXPENSE",
                    target="income_statement.interest_expense",
                    confidence=0.85,
                )
            )
        if bs_point_count < 5:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="balance_sheet:adj:request-history",
                    action="request_more_data",
                    priority="medium",
                    rationale_code="INSUFFICIENT_BALANCE_SHEET_HISTORY",
                    target="balance_sheet",
                    related_finding_ids=[finding_ids["BS030"]] if "BS030" in finding_ids else [],
                    confidence=0.85,
                )
            )
        if metadata.get("off_balance_sheet_obligations") and "BS031" not in finding_ids:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="balance_sheet:adj:off-balance-sheet",
                    action="review_assumption",
                    priority="high",
                    rationale_code="OFF_BALANCE_SHEET",
                    target="metadata.off_balance_sheet_obligations",
                    confidence=0.8,
                )
            )
        return adjustments


def _ebitda_series(income: Any) -> FinancialSeries:
    if not income.ebitda.is_empty:
        return income.ebitda
    if not income.operating_income.is_empty:
        return income.operating_income
    return income.ebit


def _build_working_capital_series(
    current_assets: FinancialSeries,
    current_liabilities: FinancialSeries,
) -> FinancialSeries:
    series = FinancialSeries(name="Working Capital", currency=current_assets.currency)
    for period in paired_periods(current_assets, current_liabilities):
        ca = current_assets.point_for(period)
        cl = current_liabilities.point_for(period)
        if ca is None or cl is None:
            continue
        series.upsert(
            FinancialPoint(
                period=period,
                value=ca.value - cl.value,
                currency=ca.currency,
                source="derived",
                confidence=mean([c for c in (ca.confidence, cl.confidence) if c is not None]),
            )
        )
    return series


def _build_quick_assets_series(bs: Any, metadata: dict[str, Any]) -> FinancialSeries:
    inventory = _series_from_metadata(
        metadata.get("inventory_by_period") or metadata.get("inventory_series"),
        name="Inventory",
        currency=bs.currency,
    )
    series = FinancialSeries(name="Quick Assets", currency=bs.currency)
    for period in paired_periods(bs.current_assets, bs.current_liabilities):
        ca = bs.current_assets.point_for(period)
        if ca is None:
            continue
        inv = inventory.point_for(period)
        inv_value = inv.value if inv is not None else 0.0
        quick_value = ca.value - inv_value
        if inv is None and not bs.cash.is_empty:
            cash = bs.cash.point_for(period)
            if cash is not None:
                quick_value = cash.value + max(0.0, ca.value - cash.value) * 0.75
        series.upsert(
            FinancialPoint(
                period=period,
                value=quick_value,
                currency=ca.currency,
                source="derived",
                confidence=ca.confidence,
            )
        )
    return series


def _resolve_net_debt(
    model: CompanyFinancialModel,
    latest_debt: float | None,
    latest_cash: float | None,
) -> float | None:
    if model.valuation_inputs.net_debt is not None:
        return model.valuation_inputs.net_debt
    if latest_debt is None and latest_cash is None:
        return None
    debt = latest_debt or 0.0
    cash = latest_cash or 0.0
    return debt - cash


def _trend_score(series: FinancialSeries) -> float | None:
    if len(series) < 2:
        return None
    direction = series.trend_direction(TREND_WINDOW)
    return {"up": 1.0, "down": -1.0, "flat": 0.0}.get(direction)


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


def _series_from_metadata(raw: Any, *, name: str, currency: str) -> FinancialSeries:
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
