"""Cash Flow rules CF001–CF006 from docs/RULE_LIBRARY.md."""

from __future__ import annotations

from analysis_engine.schemas import Evidence
from rule_library.base import RuleDefinition, RuleHit, evidence_from_metric

CASH_CONVERSION_WEAK_THRESHOLD = 0.70
CASH_CONVERSION_EXCEPTIONAL_THRESHOLD = 1.00
REVENUE_STAGNATION_THRESHOLD = 0.02


def _rule(
    rule_id: str,
    severity: str,
    finding: str,
    explanation: str,
    action: str | None = None,
) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        category="cash_flow",
        severity=severity,  # type: ignore[arg-type]
        finding=finding,
        explanation=explanation,
        suggested_analyst_action=action,
    )


CASH_FLOW_RULES: dict[str, RuleDefinition] = {
    "CF001": _rule(
        "CF001",
        "POSITIVE",
        "Consistent Cash Generation",
        "Free cash flow was positive in every year of the evaluated window.",
        "None.",
    ),
    "CF002": _rule(
        "CF002",
        "POSITIVE",
        "Exceptional Cash Conversion",
        "Operating cash flow exceeds reported net income, indicating strong cash backing.",
        "None.",
    ),
    "CF003": _rule(
        "CF003",
        "WARNING",
        "Weak Cash Conversion",
        "Operating cash flow fails to convert a healthy share of accounting earnings to cash.",
        "Review receivables, inventory, accruals, and non-cash earnings.",
    ),
    "CF004": _rule(
        "CF004",
        "CRITICAL",
        "Persistent Cash Burn",
        "Free cash flow was negative for three consecutive years.",
        "Stress-test funding needs and capital allocation priorities.",
    ),
    "CF005": _rule(
        "CF005",
        "POSITIVE",
        "Strong Economic Earnings",
        "Owner earnings rose consistently across the evaluated window.",
        "None.",
    ),
    "CF006": _rule(
        "CF006",
        "WARNING",
        "Capital Efficiency Risk",
        "Capital expenditures are rising while revenue growth is stagnant.",
        "Separate maintenance vs growth CapEx; test reinvestment returns.",
    ),
}


class CashFlowRuleInputs:
    """Computed cash-flow metrics consumed by CF001–CF006."""

    def __init__(
        self,
        *,
        cash_conversion: float | None = None,
        fcf_by_period: dict[str, float] | None = None,
        owner_earnings_by_period: dict[str, float] | None = None,
        capex_cagr: float | None = None,
        revenue_cagr: float | None = None,
        latest_fcf: float | None = None,
        period: str | None = None,
        periods: list[str] | None = None,
        evidence_by_metric: dict[str, list[Evidence]] | None = None,
    ) -> None:
        self.cash_conversion = cash_conversion
        self.fcf_by_period = fcf_by_period or {}
        self.owner_earnings_by_period = owner_earnings_by_period or {}
        self.capex_cagr = capex_cagr
        self.revenue_cagr = revenue_cagr
        self.latest_fcf = latest_fcf
        self.period = period
        self.periods = periods or []
        self.evidence_by_metric = evidence_by_metric or {}


def evaluate_cash_flow_rules(inputs: CashFlowRuleInputs) -> list[RuleHit]:
    """Evaluate CF001–CF006 against computed cash-flow metrics."""
    hits: list[RuleHit] = []
    period = inputs.period
    periods = inputs.periods

    def _ev(metric: str, value: float | None) -> list[Evidence]:
        if metric in inputs.evidence_by_metric and inputs.evidence_by_metric[metric]:
            return list(inputs.evidence_by_metric[metric])
        return [evidence_from_metric(metric=metric, value=value, period=period, confidence=0.85)]

    def _hit(rule_id: str, metrics: dict[str, float | None], metric_key: str) -> None:
        hits.append(
            RuleHit(
                rule=CASH_FLOW_RULES[rule_id],
                trigger_metrics=metrics,
                periods=periods[-5:] if periods else ([period] if period else []),
                evidence=_ev(metric_key, metrics.get(metric_key)),
            )
        )

    fcf_values = list(inputs.fcf_by_period.values())
    ordered_fcf = sorted(inputs.fcf_by_period.items(), key=lambda item: item[0])
    if len(ordered_fcf) >= 2 and all(value > 0 for _, value in ordered_fcf):
        _hit("CF001", {"FCF_POSITIVE_YEARS": float(len(ordered_fcf))}, "FCF")

    if inputs.cash_conversion is not None:
        if inputs.cash_conversion > CASH_CONVERSION_EXCEPTIONAL_THRESHOLD:
            _hit("CF002", {"CASH_CONVERSION": inputs.cash_conversion}, "CASH_CONVERSION")
        if inputs.cash_conversion < CASH_CONVERSION_WEAK_THRESHOLD:
            _hit("CF003", {"CASH_CONVERSION": inputs.cash_conversion}, "CASH_CONVERSION")

    if len(ordered_fcf) >= 3:
        last_three = [value for _, value in ordered_fcf[-3:]]
        if all(value < 0 for value in last_three):
            _hit("CF004", {"FCF": inputs.latest_fcf}, "FCF")

    oe_ordered = sorted(inputs.owner_earnings_by_period.items(), key=lambda item: item[0])
    if len(oe_ordered) >= 3:
        oe_values = [value for _, value in oe_ordered]
        if all(oe_values[i] < oe_values[i + 1] for i in range(len(oe_values) - 1)):
            _hit(
                "CF005",
                {"OWNER_EARNINGS_TREND": oe_values[-1] - oe_values[0]},
                "OWNER_EARNINGS",
            )

    if (
        inputs.capex_cagr is not None
        and inputs.revenue_cagr is not None
        and inputs.capex_cagr > 0.05
        and abs(inputs.revenue_cagr) < REVENUE_STAGNATION_THRESHOLD
    ):
        _hit(
            "CF006",
            {"CAPEX_CAGR": inputs.capex_cagr, "REV_CAGR": inputs.revenue_cagr},
            "CAPEX_RATIO",
        )

    return hits
