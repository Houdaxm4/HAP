"""Business Outlook rules OUT001–OUT030 (RULE_LIBRARY.md + extended deterministic set)."""

from __future__ import annotations

from analysis_engine.schemas import Evidence
from rule_library.base import RuleDefinition, RuleHit, evidence_from_metric


def _rule(
    rule_id: str,
    severity: str,
    finding: str,
    explanation: str,
    action: str | None = None,
) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        category="business_outlook",
        severity=severity,  # type: ignore[arg-type]
        finding=finding,
        explanation=explanation,
        suggested_analyst_action=action,
    )


BUSINESS_OUTLOOK_RULES: dict[str, RuleDefinition] = {
    "OUT001": _rule(
        "OUT001",
        "POSITIVE",
        "Positive Forward Outlook",
        "Management raised revenue guidance.",
        "None.",
    ),
    "OUT002": _rule(
        "OUT002",
        "POSITIVE",
        "Operating Outlook Improving",
        "Management expects margins to improve.",
        "None.",
    ),
    "OUT003": _rule(
        "OUT003",
        "WARNING",
        "Future Growth Expectations Reduced",
        "Management lowered long-term or forward revenue guidance.",
        "Review growth assumptions and guidance credibility.",
    ),
    "OUT004": _rule(
        "OUT004",
        "POSITIVE",
        "Favorable Industry Tailwinds",
        "Industry growth expectations are above trend and improving.",
        "None.",
    ),
    "OUT005": _rule(
        "OUT005",
        "WARNING",
        "Industry Headwinds",
        "Industry growth is weak or decelerating.",
        "Update industry growth assumptions.",
    ),
    "OUT006": _rule(
        "OUT006",
        "POSITIVE",
        "Strengthening Competitive Moat",
        "Competitive advantage and market position are improving.",
        "None.",
    ),
    "OUT007": _rule(
        "OUT007",
        "WARNING",
        "Competitive Position Deteriorating",
        "Market share or competitive advantage is weakening.",
        "Update competitive assumptions.",
    ),
    "OUT008": _rule(
        "OUT008",
        "POSITIVE",
        "Strong Pricing Power Outlook",
        "Forward pricing power appears durable.",
        "None.",
    ),
    "OUT009": _rule(
        "OUT009",
        "WARNING",
        "Pricing Pressure Expected",
        "Pricing power is limited or expected to weaken.",
        "Review margin and pricing assumptions.",
    ),
    "OUT010": _rule(
        "OUT010",
        "POSITIVE",
        "Robust Product Pipeline",
        "Product pipeline supports future growth.",
        "None.",
    ),
    "OUT011": _rule(
        "OUT011",
        "WARNING",
        "Weak Product Pipeline",
        "Product pipeline appears thin or aging.",
        "Request product roadmap detail.",
    ),
    "OUT012": _rule(
        "OUT012",
        "POSITIVE",
        "Geographic Expansion Opportunity",
        "Geographic expansion offers incremental growth.",
        "None.",
    ),
    "OUT013": _rule(
        "OUT013",
        "WARNING",
        "Customer Concentration Risk",
        "Revenue is concentrated among few customers.",
        "Model customer loss scenarios.",
    ),
    "OUT014": _rule(
        "OUT014",
        "WARNING",
        "Supplier Concentration Risk",
        "Operations depend on concentrated suppliers.",
        "Review supply chain resilience.",
    ),
    "OUT015": _rule(
        "OUT015",
        "WARNING",
        "Regulatory Headwinds",
        "Regulatory exposure is elevated and/or worsening.",
        "Monitor regulatory developments.",
    ),
    "OUT016": _rule(
        "OUT016",
        "POSITIVE",
        "Favorable Regulatory Environment",
        "Regulatory exposure is limited or improving.",
        "None.",
    ),
    "OUT017": _rule(
        "OUT017",
        "CRITICAL",
        "Technological Disruption Risk",
        "Technology disruption threatens the business model.",
        "Reassess long-term demand and moat durability.",
    ),
    "OUT018": _rule(
        "OUT018",
        "POSITIVE",
        "Technology Leadership",
        "Disruption risk is low relative to industry peers.",
        "None.",
    ),
    "OUT019": _rule(
        "OUT019",
        "POSITIVE",
        "Credible Management Guidance",
        "Historical guidance accuracy supports forward forecasts.",
        "None.",
    ),
    "OUT020": _rule(
        "OUT020",
        "WARNING",
        "Low Guidance Credibility",
        "Management has a weak track record of meeting guidance.",
        "Challenge management guidance.",
    ),
    "OUT021": _rule(
        "OUT021",
        "WARNING",
        "Cyclical Downturn Exposure",
        "Business is highly cyclical and exposed to downturn risk.",
        "Stress-test cyclical downside.",
    ),
    "OUT022": _rule(
        "OUT022",
        "POSITIVE",
        "Cyclical Recovery Opportunity",
        "Cycle positioning suggests recovery upside.",
        "None.",
    ),
    "OUT023": _rule(
        "OUT023",
        "POSITIVE",
        "Margin Expansion Runway",
        "Operating leverage or mix shift supports margin expansion.",
        "None.",
    ),
    "OUT024": _rule(
        "OUT024",
        "WARNING",
        "Margin Compression Risk",
        "Forward indicators suggest margin pressure ahead.",
        "Review margin forecast assumptions.",
    ),
    "OUT025": _rule(
        "OUT025",
        "POSITIVE",
        "Constructive Capital Allocation Plans",
        "Stated capital allocation plans support value creation.",
        "None.",
    ),
    "OUT026": _rule(
        "OUT026",
        "POSITIVE",
        "Structural Growth Catalyst",
        "Identified structural catalyst supports sustained growth.",
        "None.",
    ),
    "OUT027": _rule(
        "OUT027",
        "CRITICAL",
        "Structural Decline Risk",
        "Structural forces may permanently impair demand or returns.",
        "Reassess terminal value and growth assumptions.",
    ),
    "OUT028": _rule(
        "OUT028",
        "INFO",
        "Insufficient Outlook Data",
        "Too little forward-looking evidence to assess outlook confidently.",
        "Request industry research and management outlook inputs.",
    ),
    "OUT029": _rule(
        "OUT029",
        "POSITIVE",
        "Balanced Forward Outlook",
        "Forward catalysts and risks appear broadly balanced.",
        "None.",
    ),
    "OUT030": _rule(
        "OUT030",
        "WARNING",
        "Material Outlook Uncertainty",
        "Multiple forward indicators carry elevated uncertainty.",
        "Reduce forecast conviction until evidence improves.",
    ),
}


class BusinessOutlookRuleInputs:
    def __init__(
        self,
        *,
        industry_growth_rate: float | None = None,
        industry_growth_trend: float | None = None,
        moat_score: float | None = None,
        market_share_trend: float | None = None,
        advantage_trend: float | None = None,
        pricing_power_score: float | None = None,
        product_pipeline_strength: float | None = None,
        geographic_expansion_potential: float | None = None,
        customer_concentration: float | None = None,
        supplier_concentration: float | None = None,
        regulatory_exposure: float | None = None,
        regulatory_trend: float | None = None,
        technological_disruption_risk: float | None = None,
        revenue_guidance_trend: float | None = None,
        margin_guidance_trend: float | None = None,
        guidance_accuracy_score: float | None = None,
        cyclicality_exposure: float | None = None,
        cycle_position_score: float | None = None,
        capital_allocation_plan_score: float | None = None,
        margin_expansion_potential: float | None = None,
        structural_growth_catalyst: float | None = None,
        structural_decline_risk: float | None = None,
        outlook_field_count: int = 0,
        outlook_confidence_avg: float | None = None,
        period: str | None = None,
        evidence_by_metric: dict[str, list[Evidence]] | None = None,
    ) -> None:
        self.industry_growth_rate = industry_growth_rate
        self.industry_growth_trend = industry_growth_trend
        self.moat_score = moat_score
        self.market_share_trend = market_share_trend
        self.advantage_trend = advantage_trend
        self.pricing_power_score = pricing_power_score
        self.product_pipeline_strength = product_pipeline_strength
        self.geographic_expansion_potential = geographic_expansion_potential
        self.customer_concentration = customer_concentration
        self.supplier_concentration = supplier_concentration
        self.regulatory_exposure = regulatory_exposure
        self.regulatory_trend = regulatory_trend
        self.technological_disruption_risk = technological_disruption_risk
        self.revenue_guidance_trend = revenue_guidance_trend
        self.margin_guidance_trend = margin_guidance_trend
        self.guidance_accuracy_score = guidance_accuracy_score
        self.cyclicality_exposure = cyclicality_exposure
        self.cycle_position_score = cycle_position_score
        self.capital_allocation_plan_score = capital_allocation_plan_score
        self.margin_expansion_potential = margin_expansion_potential
        self.structural_growth_catalyst = structural_growth_catalyst
        self.structural_decline_risk = structural_decline_risk
        self.outlook_field_count = outlook_field_count
        self.outlook_confidence_avg = outlook_confidence_avg
        self.period = period
        self.evidence_by_metric = evidence_by_metric or {}


def evaluate_business_outlook_rules(inputs: BusinessOutlookRuleInputs) -> list[RuleHit]:
    hits: list[RuleHit] = []
    period = inputs.period

    def _ev(metric: str, value: float | None) -> list[Evidence]:
        if metric in inputs.evidence_by_metric and inputs.evidence_by_metric[metric]:
            return list(inputs.evidence_by_metric[metric])
        return [evidence_from_metric(metric=metric, value=value, period=period, confidence=0.65)]

    def _hit(rule_id: str, metrics: dict[str, float | None], metric_key: str) -> None:
        hits.append(
            RuleHit(
                rule=BUSINESS_OUTLOOK_RULES[rule_id],
                trigger_metrics=metrics,
                periods=[period] if period else [],
                evidence=_ev(metric_key, metrics.get(metric_key)),
            )
        )

    if inputs.outlook_field_count < 3:
        _hit("OUT028", {"OUTLOOK_FIELD_COUNT": float(inputs.outlook_field_count)}, "OUTLOOK_FIELD_COUNT")

    if inputs.revenue_guidance_trend is not None and inputs.revenue_guidance_trend >= 0.50:
        _hit(
            "OUT001",
            {"REVENUE_GUIDANCE_TREND": inputs.revenue_guidance_trend},
            "REVENUE_GUIDANCE_TREND",
        )

    if inputs.margin_guidance_trend is not None and inputs.margin_guidance_trend >= 0.30:
        _hit(
            "OUT002",
            {"MARGIN_GUIDANCE_TREND": inputs.margin_guidance_trend},
            "MARGIN_GUIDANCE_TREND",
        )

    if inputs.revenue_guidance_trend is not None and inputs.revenue_guidance_trend <= -0.50:
        _hit(
            "OUT003",
            {"REVENUE_GUIDANCE_TREND": inputs.revenue_guidance_trend},
            "REVENUE_GUIDANCE_TREND",
        )

    if (
        inputs.industry_growth_rate is not None
        and inputs.industry_growth_rate >= 0.04
        and inputs.industry_growth_trend is not None
        and inputs.industry_growth_trend >= 0.10
    ):
        _hit(
            "OUT004",
            {
                "INDUSTRY_GROWTH_RATE": inputs.industry_growth_rate,
                "INDUSTRY_GROWTH_TREND": inputs.industry_growth_trend,
            },
            "INDUSTRY_GROWTH_RATE",
        )

    if (
        inputs.industry_growth_rate is not None
        and inputs.industry_growth_rate < 0.01
    ) or (
        inputs.industry_growth_trend is not None and inputs.industry_growth_trend <= -0.20
    ):
        _hit(
            "OUT005",
            {
                "INDUSTRY_GROWTH_RATE": inputs.industry_growth_rate,
                "INDUSTRY_GROWTH_TREND": inputs.industry_growth_trend,
            },
            "INDUSTRY_GROWTH_RATE",
        )

    if (
        inputs.moat_score is not None
        and inputs.moat_score >= 0.70
        and inputs.advantage_trend is not None
        and inputs.advantage_trend >= 0.05
    ):
        _hit(
            "OUT006",
            {"MOAT_SCORE": inputs.moat_score, "ADVANTAGE_TREND": inputs.advantage_trend},
            "MOAT_SCORE",
        )

    if (
        inputs.market_share_trend is not None
        and inputs.market_share_trend <= -0.15
    ) or (
        inputs.advantage_trend is not None and inputs.advantage_trend <= -0.10
    ):
        _hit(
            "OUT007",
            {
                "MARKET_SHARE_TREND": inputs.market_share_trend,
                "ADVANTAGE_TREND": inputs.advantage_trend,
            },
            "MARKET_SHARE_TREND",
        )

    if inputs.pricing_power_score is not None and inputs.pricing_power_score >= 0.75:
        _hit("OUT008", {"PRICING_POWER_SCORE": inputs.pricing_power_score}, "PRICING_POWER_SCORE")

    if inputs.pricing_power_score is not None and inputs.pricing_power_score <= 0.35:
        _hit("OUT009", {"PRICING_POWER_SCORE": inputs.pricing_power_score}, "PRICING_POWER_SCORE")

    if inputs.product_pipeline_strength is not None and inputs.product_pipeline_strength >= 0.70:
        _hit(
            "OUT010",
            {"PRODUCT_PIPELINE_STRENGTH": inputs.product_pipeline_strength},
            "PRODUCT_PIPELINE_STRENGTH",
        )

    if inputs.product_pipeline_strength is not None and inputs.product_pipeline_strength <= 0.30:
        _hit(
            "OUT011",
            {"PRODUCT_PIPELINE_STRENGTH": inputs.product_pipeline_strength},
            "PRODUCT_PIPELINE_STRENGTH",
        )

    if (
        inputs.geographic_expansion_potential is not None
        and inputs.geographic_expansion_potential >= 0.60
    ):
        _hit(
            "OUT012",
            {"GEOGRAPHIC_EXPANSION_POTENTIAL": inputs.geographic_expansion_potential},
            "GEOGRAPHIC_EXPANSION_POTENTIAL",
        )

    if inputs.customer_concentration is not None and inputs.customer_concentration >= 0.25:
        _hit(
            "OUT013",
            {"CUSTOMER_CONCENTRATION": inputs.customer_concentration},
            "CUSTOMER_CONCENTRATION",
        )

    if inputs.supplier_concentration is not None and inputs.supplier_concentration >= 0.35:
        _hit(
            "OUT014",
            {"SUPPLIER_CONCENTRATION": inputs.supplier_concentration},
            "SUPPLIER_CONCENTRATION",
        )

    if (
        inputs.regulatory_exposure is not None
        and inputs.regulatory_exposure >= 0.55
    ) or (
        inputs.regulatory_trend is not None
        and inputs.regulatory_trend <= -0.20
        and inputs.regulatory_exposure is not None
        and inputs.regulatory_exposure >= 0.35
    ):
        _hit(
            "OUT015",
            {
                "REGULATORY_EXPOSURE": inputs.regulatory_exposure,
                "REGULATORY_TREND": inputs.regulatory_trend,
            },
            "REGULATORY_EXPOSURE",
        )

    if (
        inputs.regulatory_exposure is not None
        and inputs.regulatory_exposure <= 0.25
        and (inputs.regulatory_trend is None or inputs.regulatory_trend >= 0)
    ):
        _hit("OUT016", {"REGULATORY_EXPOSURE": inputs.regulatory_exposure}, "REGULATORY_EXPOSURE")

    if inputs.technological_disruption_risk is not None and inputs.technological_disruption_risk >= 0.70:
        _hit(
            "OUT017",
            {"TECH_DISRUPTION_RISK": inputs.technological_disruption_risk},
            "TECH_DISRUPTION_RISK",
        )

    if (
        inputs.technological_disruption_risk is not None
        and inputs.technological_disruption_risk <= 0.25
        and inputs.moat_score is not None
        and inputs.moat_score >= 0.65
    ):
        _hit(
            "OUT018",
            {
                "TECH_DISRUPTION_RISK": inputs.technological_disruption_risk,
                "MOAT_SCORE": inputs.moat_score,
            },
            "TECH_DISRUPTION_RISK",
        )

    if inputs.guidance_accuracy_score is not None and inputs.guidance_accuracy_score >= 0.80:
        _hit(
            "OUT019",
            {"GUIDANCE_ACCURACY_SCORE": inputs.guidance_accuracy_score},
            "GUIDANCE_ACCURACY_SCORE",
        )

    if inputs.guidance_accuracy_score is not None and inputs.guidance_accuracy_score <= 0.45:
        _hit(
            "OUT020",
            {"GUIDANCE_ACCURACY_SCORE": inputs.guidance_accuracy_score},
            "GUIDANCE_ACCURACY_SCORE",
        )

    if (
        inputs.cyclicality_exposure is not None
        and inputs.cyclicality_exposure >= 0.65
        and (inputs.cycle_position_score is None or inputs.cycle_position_score <= 0)
    ):
        _hit(
            "OUT021",
            {
                "CYCLICALITY_EXPOSURE": inputs.cyclicality_exposure,
                "CYCLE_POSITION_SCORE": inputs.cycle_position_score,
            },
            "CYCLICALITY_EXPOSURE",
        )

    if (
        inputs.cyclicality_exposure is not None
        and inputs.cyclicality_exposure >= 0.40
        and inputs.cycle_position_score is not None
        and inputs.cycle_position_score >= 0.50
    ):
        _hit(
            "OUT022",
            {
                "CYCLICALITY_EXPOSURE": inputs.cyclicality_exposure,
                "CYCLE_POSITION_SCORE": inputs.cycle_position_score,
            },
            "CYCLE_POSITION_SCORE",
        )

    if inputs.margin_expansion_potential is not None and inputs.margin_expansion_potential >= 0.20:
        _hit(
            "OUT023",
            {"MARGIN_EXPANSION_POTENTIAL": inputs.margin_expansion_potential},
            "MARGIN_EXPANSION_POTENTIAL",
        )

    if (
        inputs.margin_guidance_trend is not None
        and inputs.margin_guidance_trend <= -0.30
    ) or (
        inputs.margin_expansion_potential is not None
        and inputs.margin_expansion_potential <= 0.0
        and inputs.pricing_power_score is not None
        and inputs.pricing_power_score <= 0.40
    ):
        _hit(
            "OUT024",
            {
                "MARGIN_GUIDANCE_TREND": inputs.margin_guidance_trend,
                "MARGIN_EXPANSION_POTENTIAL": inputs.margin_expansion_potential,
            },
            "MARGIN_GUIDANCE_TREND",
        )

    if (
        inputs.capital_allocation_plan_score is not None
        and inputs.capital_allocation_plan_score >= 0.70
    ):
        _hit(
            "OUT025",
            {"CAPITAL_ALLOCATION_PLAN_SCORE": inputs.capital_allocation_plan_score},
            "CAPITAL_ALLOCATION_PLAN_SCORE",
        )

    if (
        inputs.structural_growth_catalyst is not None
        and inputs.structural_growth_catalyst >= 0.65
    ):
        _hit(
            "OUT026",
            {"STRUCTURAL_GROWTH_CATALYST": inputs.structural_growth_catalyst},
            "STRUCTURAL_GROWTH_CATALYST",
        )

    if inputs.structural_decline_risk is not None and inputs.structural_decline_risk >= 0.65:
        _hit(
            "OUT027",
            {"STRUCTURAL_DECLINE_RISK": inputs.structural_decline_risk},
            "STRUCTURAL_DECLINE_RISK",
        )

    positive_signals = sum(
        1
        for flag in (
            inputs.revenue_guidance_trend is not None and inputs.revenue_guidance_trend > 0,
            inputs.moat_score is not None and inputs.moat_score >= 0.65,
            inputs.product_pipeline_strength is not None and inputs.product_pipeline_strength >= 0.60,
            inputs.structural_growth_catalyst is not None and inputs.structural_growth_catalyst >= 0.50,
        )
        if flag
    )
    negative_signals = sum(
        1
        for flag in (
            inputs.revenue_guidance_trend is not None and inputs.revenue_guidance_trend < 0,
            inputs.structural_decline_risk is not None and inputs.structural_decline_risk >= 0.50,
            inputs.technological_disruption_risk is not None
            and inputs.technological_disruption_risk >= 0.55,
            inputs.regulatory_exposure is not None and inputs.regulatory_exposure >= 0.55,
        )
        if flag
    )
    if (
        inputs.outlook_field_count >= 5
        and positive_signals >= 2
        and negative_signals <= 1
        and "OUT028" not in {hit.rule.rule_id for hit in hits}
    ):
        _hit("OUT029", {"POSITIVE_SIGNALS": float(positive_signals)}, "POSITIVE_SIGNALS")

    if (
        inputs.outlook_confidence_avg is not None
        and inputs.outlook_confidence_avg < 0.55
        and inputs.outlook_field_count >= 3
    ):
        _hit(
            "OUT030",
            {"OUTLOOK_CONFIDENCE_AVG": inputs.outlook_confidence_avg},
            "OUTLOOK_CONFIDENCE_AVG",
        )

    return hits
