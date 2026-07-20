"""Growth rules GR001–GR032 from docs/modules/GROWTH_MODULE_SPEC.md."""

from __future__ import annotations

from typing import Any

from analysis_engine.schemas import Evidence
from rule_library.base import RuleDefinition, RuleHit, evidence_from_metric

DEFAULT_INFLATION_RATE = 0.03


def _rule(
    rule_id: str,
    severity: str,
    finding: str,
    explanation: str,
    action: str | None = None,
) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        category="growth",
        severity=severity,  # type: ignore[arg-type]
        finding=finding,
        explanation=explanation,
        suggested_analyst_action=action,
    )


GROWTH_RULES: dict[str, RuleDefinition] = {
    "GR001": _rule(
        "GR001",
        "POSITIVE",
        "Exceptional Revenue Growth",
        "Multi-year revenue compounding exceeds the exceptional growth threshold.",
        "Confirm growth is organic and cash-backed; no automatic adjustment.",
    ),
    "GR002": _rule(
        "GR002",
        "POSITIVE",
        "Healthy Revenue Growth",
        "Revenue compounds at a healthy long-term rate.",
        "None.",
    ),
    "GR003": _rule(
        "GR003",
        "WARNING",
        "Weak Organic Growth",
        "Top-line growth fails to outpace inflation, implying weak real expansion.",
        "Check pricing power, volume trends, and discontinued operations.",
    ),
    "GR004": _rule(
        "GR004",
        "POSITIVE",
        "Operating Leverage Improving",
        "Earnings are compounding faster than revenue.",
        "Verify margin expansion is sustainable, not one-time cost cuts.",
    ),
    "GR005": _rule(
        "GR005",
        "WARNING",
        "Low Quality Growth",
        "Sales expand while free cash flow contracts.",
        "Inspect WC, CapEx intensity, and cash conversion.",
    ),
    "GR006": _rule(
        "GR006",
        "WARNING",
        "Shareholder Dilution",
        "Persistent share issuance dilutes ownership.",
        "Review equity compensation and issuance; prefer per-share metrics.",
    ),
    "GR007": _rule(
        "GR007",
        "WARNING",
        "Acquisition Driven Growth",
        "Reported growth appears dependent on acquisitions rather than organic demand.",
        "Separate organic growth; normalize acquisition effects.",
    ),
    "GR008": _rule(
        "GR008",
        "POSITIVE",
        "Exceptional Earnings Growth",
        "Diluted EPS compounds at an exceptional rate.",
        "Confirm not driven solely by buybacks or one-time tax items.",
    ),
    "GR009": _rule(
        "GR009",
        "WARNING",
        "Negative Earnings Growth",
        "Shareholder earnings are contracting on a multi-year basis.",
        "Separate cyclical vs structural decline.",
    ),
    "GR010": _rule(
        "GR010",
        "POSITIVE",
        "Exceptional Cash Flow Growth",
        "Free cash flow is compounding strongly.",
        "None.",
    ),
    "GR011": _rule(
        "GR011",
        "CRITICAL",
        "Cash-Consuming Expansion",
        "The business is growing sales while burning cash.",
        "Stress-test funding needs and reinvestment returns.",
    ),
    "GR012": _rule(
        "GR012",
        "INFO",
        "Revenue Stagnation",
        "Top line is roughly flat in nominal terms.",
        "Evaluate whether maturity is acceptable given returns on capital (other modules).",
    ),
    "GR013": _rule(
        "GR013",
        "CRITICAL",
        "Structural Revenue Decline",
        "Multi-year revenue contraction indicates franchise pressure.",
        "Assess disruption, share loss, and turnaround credibility.",
    ),
    "GR014": _rule(
        "GR014",
        "POSITIVE",
        "Cash-Backed Growth",
        "Cash generation keeps pace with top-line expansion.",
        "None.",
    ),
    "GR015": _rule(
        "GR015",
        "WARNING",
        "Accrual Growth Risk",
        "Accounting earnings grow while free cash flow does not.",
        "Review receivables, capitalization policies, and non-cash earnings.",
    ),
    "GR016": _rule(
        "GR016",
        "POSITIVE",
        "Anti-Dilutive Expansion",
        "Revenue grows while share count shrinks — supportive of per-share value.",
        "Confirm buybacks are not debt-funded beyond prudence (Balance Sheet module).",
    ),
    "GR017": _rule(
        "GR017",
        "WARNING",
        "Dilution Exceeds Top-Line Growth",
        "Consolidated growth is negated on a per-share basis.",
        "Recast growth on per-share metrics for investment debate.",
    ),
    "GR018": _rule(
        "GR018",
        "POSITIVE",
        "Strong Book Value Compounding",
        "Equity book value compounds at a healthy rate.",
        "Check whether AOCI / buybacks distort book trends.",
    ),
    "GR019": _rule(
        "GR019",
        "POSITIVE",
        "Stable Growth",
        "Positive growth with low volatility of yearly growth rates.",
        "None.",
    ),
    "GR020": _rule(
        "GR020",
        "WARNING",
        "Unstable Growth",
        "Growth rates swing widely, reducing forecast reliability.",
        "Prefer longer windows; normalize one-time spikes.",
    ),
    "GR021": _rule(
        "GR021",
        "POSITIVE",
        "Persistent Growth",
        "Revenue rose in most observed years.",
        "None.",
    ),
    "GR022": _rule(
        "GR022",
        "WARNING",
        "Growth Deceleration",
        "Recent growth is materially slower than the prior sub-period.",
        "Update outlook assumptions; avoid extrapolating old CAGR.",
    ),
    "GR023": _rule(
        "GR023",
        "POSITIVE",
        "Growth Acceleration",
        "Recent growth is materially faster than the prior sub-period.",
        "Test durability vs easy comps / temporary stimulus.",
    ),
    "GR024": _rule(
        "GR024",
        "WARNING",
        "Boom-Bust Growth Pattern",
        "Extreme positive and negative years appear in the same window.",
        "Normalize cycle; do not treat peak CAGR as base case.",
    ),
    "GR025": _rule(
        "GR025",
        "WARNING",
        "Hypergrowth Sustainability Risk",
        "Extremely high compounding rarely persists; fade risk is elevated.",
        "Use fade assumptions in outlook/valuation; stress-test.",
    ),
    "GR026": _rule(
        "GR026",
        "INFO",
        "Possible Base-Effect Distortion",
        "Pandemic-period base effects may distort CAGR.",
        "Propose COVID-normalized growth series via analyst adjustment.",
    ),
    "GR027": _rule(
        "GR027",
        "WARNING",
        "One-Time Revenue Spike Suspected",
        "Latest growth far exceeds recent history.",
        "Remove one-time revenue; recompute organic CAGR.",
    ),
    "GR028": _rule(
        "GR028",
        "WARNING",
        "Discontinued Operations Distortion",
        "Reported growth may be non-comparable across periods.",
        "Restate continuing-operations growth series.",
    ),
    "GR029": _rule(
        "GR029",
        "INFO",
        "Book Value Growth Not Meaningful",
        "Book CAGR is unreliable with zero/negative equity.",
        "Ignore BV_CAGR; rely on revenue/EPS/FCF growth.",
    ),
    "GR030": _rule(
        "GR030",
        "WARNING",
        "Insufficient Growth History",
        "Too little history for robust multi-year growth conclusions.",
        "Lower confidence; request longer series before high-conviction use.",
    ),
    "GR031": _rule(
        "GR031",
        "POSITIVE",
        "Strong Organic Growth",
        "Growth is primarily organic at a healthy rate.",
        "None.",
    ),
    "GR032": _rule(
        "GR032",
        "CRITICAL",
        "Acquisitions Masking Organic Decline",
        "Reported growth hides contracting organic demand.",
        "Treat organic decline as primary growth truth; normalize.",
    ),
}


class GrowthRuleInputs:
    """Computed metrics consumed by growth rules."""

    def __init__(
        self,
        *,
        rev_cagr: float | None = None,
        eps_cagr: float | None = None,
        fcf_cagr: float | None = None,
        oi_cagr: float | None = None,
        bv_cagr: float | None = None,
        organic_rev_cagr: float | None = None,
        inorganic_rev_share: float | None = None,
        share_count_cagr: float | None = None,
        rev_per_share_cagr: float | None = None,
        growth_stability: float | None = None,
        growth_volatility: float | None = None,
        growth_persistence: float | None = None,
        growth_acceleration: float | None = None,
        rev_yoy: float | None = None,
        rev_yoy_by_period: dict[str, float] | None = None,
        latest_fcf: float | None = None,
        revenue_point_count: int = 0,
        eps_point_count: int = 0,
        equity_nonpositive_in_window: bool = False,
        organic_data_available: bool = False,
        inflation_rate: float = DEFAULT_INFLATION_RATE,
        metadata: dict[str, Any] | None = None,
        period: str | None = None,
        periods: list[str] | None = None,
        evidence_by_metric: dict[str, list[Evidence]] | None = None,
    ) -> None:
        self.rev_cagr = rev_cagr
        self.eps_cagr = eps_cagr
        self.fcf_cagr = fcf_cagr
        self.oi_cagr = oi_cagr
        self.bv_cagr = bv_cagr
        self.organic_rev_cagr = organic_rev_cagr
        self.inorganic_rev_share = inorganic_rev_share
        self.share_count_cagr = share_count_cagr
        self.rev_per_share_cagr = rev_per_share_cagr
        self.growth_stability = growth_stability
        self.growth_volatility = growth_volatility
        self.growth_persistence = growth_persistence
        self.growth_acceleration = growth_acceleration
        self.rev_yoy = rev_yoy
        self.rev_yoy_by_period = rev_yoy_by_period or {}
        self.latest_fcf = latest_fcf
        self.revenue_point_count = revenue_point_count
        self.eps_point_count = eps_point_count
        self.equity_nonpositive_in_window = equity_nonpositive_in_window
        self.organic_data_available = organic_data_available
        self.inflation_rate = inflation_rate
        self.metadata = metadata or {}
        self.period = period
        self.periods = periods or []
        self.evidence_by_metric = evidence_by_metric or {}


def evaluate_growth_rules(inputs: GrowthRuleInputs) -> list[RuleHit]:
    """Evaluate GR001–GR032 against computed growth metrics."""
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
                rule=GROWTH_RULES[rule_id],
                trigger_metrics=metrics,
                periods=periods[-5:] if periods else ([period] if period else []),
                evidence=_ev(metric_key, metrics.get(metric_key)),
            )
        )

    rev = inputs.rev_cagr
    eps = inputs.eps_cagr
    fcf = inputs.fcf_cagr

    if rev is not None and inputs.revenue_point_count >= 3:
        if rev > 0.15:
            _hit("GR001", {"REV_CAGR": rev}, "REV_CAGR")
        if 0.08 <= rev <= 0.15:
            _hit("GR002", {"REV_CAGR": rev}, "REV_CAGR")
        if rev < inputs.inflation_rate:
            _hit(
                "GR003",
                {"REV_CAGR": rev, "INFLATION_RATE": inputs.inflation_rate},
                "REV_CAGR",
            )
        if abs(rev) < 0.02:
            _hit("GR012", {"REV_CAGR": rev}, "REV_CAGR")
        if rev <= -0.05:
            _hit("GR013", {"REV_CAGR": rev}, "REV_CAGR")
        if rev > 0.30:
            _hit("GR025", {"REV_CAGR": rev}, "REV_CAGR")

    if (
        eps is not None
        and rev is not None
        and rev > 0
        and eps > rev + 0.02
    ):
        _hit("GR004", {"EPS_CAGR": eps, "REV_CAGR": rev}, "EPS_CAGR")

    if rev is not None and fcf is not None and rev > 0 and fcf < 0:
        _hit("GR005", {"REV_CAGR": rev, "FCF_CAGR": fcf}, "FCF_CAGR")

    if inputs.share_count_cagr is not None and _share_count_always_increasing(inputs):
        _hit("GR006", {"SHARE_COUNT_CAGR": inputs.share_count_cagr}, "SHARE_COUNT_CAGR")

    acquisition_flag = bool(
        inputs.metadata.get("acquisition_primary_growth")
        or inputs.metadata.get("acquisition_driven_growth")
    )
    if (inputs.inorganic_rev_share is not None and inputs.inorganic_rev_share >= 0.30) or acquisition_flag:
        _hit(
            "GR007",
            {"INORGANIC_REV_SHARE": inputs.inorganic_rev_share},
            "INORGANIC_REV_SHARE",
        )

    if eps is not None and inputs.eps_point_count >= 3:
        if eps > 0.20:
            _hit("GR008", {"EPS_CAGR": eps}, "EPS_CAGR")
        if eps < 0:
            _hit("GR009", {"EPS_CAGR": eps}, "EPS_CAGR")

    if fcf is not None and inputs.latest_fcf is not None and fcf > 0.15 and inputs.latest_fcf > 0:
        _hit("GR010", {"FCF_CAGR": fcf, "FCF": inputs.latest_fcf}, "FCF_CAGR")

    if (
        inputs.latest_fcf is not None
        and inputs.latest_fcf < 0
        and rev is not None
        and rev > 0.05
    ):
        _hit("GR011", {"FCF": inputs.latest_fcf, "REV_CAGR": rev}, "FCF")

    if (
        fcf is not None
        and rev is not None
        and rev > 0
        and inputs.latest_fcf is not None
        and inputs.latest_fcf > 0
        and fcf >= rev - 0.02
    ):
        _hit("GR014", {"FCF_CAGR": fcf, "REV_CAGR": rev}, "FCF_CAGR")

    if eps is not None and fcf is not None and eps > 0.05 and fcf < 0:
        _hit("GR015", {"EPS_CAGR": eps, "FCF_CAGR": fcf}, "EPS_CAGR")

    if (
        inputs.share_count_cagr is not None
        and rev is not None
        and inputs.share_count_cagr < 0
        and rev > 0
    ):
        _hit("GR016", {"SHARE_COUNT_CAGR": inputs.share_count_cagr, "REV_CAGR": rev}, "SHARE_COUNT_CAGR")

    if (
        rev is not None
        and inputs.rev_per_share_cagr is not None
        and rev > 0
        and inputs.rev_per_share_cagr < 0
    ):
        _hit(
            "GR017",
            {"REV_CAGR": rev, "REV_PER_SHARE_CAGR": inputs.rev_per_share_cagr},
            "REV_PER_SHARE_CAGR",
        )

    if inputs.bv_cagr is not None and inputs.bv_cagr >= 0.08 and not inputs.equity_nonpositive_in_window:
        _hit("GR018", {"BV_CAGR": inputs.bv_cagr}, "BV_CAGR")

    if (
        inputs.growth_stability is not None
        and rev is not None
        and inputs.growth_stability >= 0.70
        and rev > 0
    ):
        _hit("GR019", {"GROWTH_STABILITY": inputs.growth_stability, "REV_CAGR": rev}, "GROWTH_STABILITY")

    if (
        (inputs.growth_volatility is not None and inputs.growth_volatility > 0.80)
        or (inputs.growth_stability is not None and inputs.growth_stability < 0.40)
    ):
        _hit(
            "GR020",
            {
                "GROWTH_VOLATILITY": inputs.growth_volatility,
                "GROWTH_STABILITY": inputs.growth_stability,
            },
            "GROWTH_VOLATILITY",
        )

    if (
        inputs.growth_persistence is not None
        and len(inputs.rev_yoy_by_period) >= 5
        and inputs.growth_persistence >= 0.80
    ):
        _hit("GR021", {"GROWTH_PERSISTENCE": inputs.growth_persistence}, "GROWTH_PERSISTENCE")

    if inputs.growth_acceleration is not None:
        if inputs.growth_acceleration <= -0.05:
            _hit("GR022", {"GROWTH_ACCELERATION": inputs.growth_acceleration}, "GROWTH_ACCELERATION")
        if (
            inputs.growth_acceleration >= 0.05
            and inputs.rev_yoy is not None
            and inputs.rev_yoy > 0
        ):
            _hit("GR023", {"GROWTH_ACCELERATION": inputs.growth_acceleration}, "GROWTH_ACCELERATION")

    yoy_values = list(inputs.rev_yoy_by_period.values())
    if any(v > 0.25 for v in yoy_values) and any(v < -0.10 for v in yoy_values):
        _hit("GR024", {"REV_YOY_MAX": max(yoy_values), "REV_YOY_MIN": min(yoy_values)}, "REV_YOY")

    if _covid_base_effect(inputs):
        _hit("GR026", {"REV_YOY": inputs.rev_yoy}, "REV_YOY")

    if _one_time_spike(inputs):
        _hit("GR027", {"REV_YOY": inputs.rev_yoy}, "REV_YOY")

    if bool(inputs.metadata.get("discontinued_operations_impact")) or bool(
        inputs.metadata.get("discontinued_operations")
    ):
        _hit("GR028", {"FLAG": 1.0}, "DISCONTINUED_OPS")

    if inputs.equity_nonpositive_in_window:
        _hit("GR029", {"BV_CAGR": inputs.bv_cagr}, "BV_CAGR")

    if inputs.revenue_point_count < 3:
        _hit("GR030", {"REV_HISTORY_YEARS": float(inputs.revenue_point_count)}, "REV_HISTORY_YEARS")

    if (
        inputs.organic_data_available
        and inputs.organic_rev_cagr is not None
        and inputs.inorganic_rev_share is not None
        and inputs.organic_rev_cagr >= 0.08
        and inputs.inorganic_rev_share < 0.20
    ):
        _hit(
            "GR031",
            {
                "ORGANIC_REV_CAGR": inputs.organic_rev_cagr,
                "INORGANIC_REV_SHARE": inputs.inorganic_rev_share,
            },
            "ORGANIC_REV_CAGR",
        )

    if (
        inputs.organic_data_available
        and rev is not None
        and inputs.organic_rev_cagr is not None
        and rev > 0
        and inputs.organic_rev_cagr < 0
    ):
        _hit(
            "GR032",
            {"REV_CAGR": rev, "ORGANIC_REV_CAGR": inputs.organic_rev_cagr},
            "ORGANIC_REV_CAGR",
        )

    return hits


def _share_count_always_increasing(inputs: GrowthRuleInputs) -> bool:
    """GR006 requires share count up every year; use metadata series when present."""
    series = inputs.metadata.get("share_count_series")
    if isinstance(series, dict) and len(series) >= 3:
        values = [float(series[k]) for k in sorted(series.keys())]
        return all(values[i] < values[i + 1] for i in range(len(values) - 1))
    if isinstance(series, list) and len(series) >= 3:
        points = sorted(series, key=lambda item: str(item.get("period", "")))
        values = [float(item["value"]) for item in points]
        return all(values[i] < values[i + 1] for i in range(len(values) - 1))
    # Fallback: positive share-count CAGR alone is not enough for "every year".
    return False


def _covid_base_effect(inputs: GrowthRuleInputs) -> bool:
    if bool(inputs.metadata.get("normalize_covid")):
        return True
    for period, yoy in inputs.rev_yoy_by_period.items():
        if ("2020" in period or "2021" in period) and abs(yoy) > 0.40:
            return True
    return False


def _one_time_spike(inputs: GrowthRuleInputs) -> bool:
    if inputs.rev_yoy is None or inputs.rev_yoy <= 0.40:
        return False
    ordered = sorted(inputs.rev_yoy_by_period.items(), key=lambda item: item[0])
    if len(ordered) < 4:
        return False
    prior = [value for _, value in ordered[-4:-1]]
    if len(prior) < 3:
        return False
    return (sum(prior) / len(prior)) < 0.10
