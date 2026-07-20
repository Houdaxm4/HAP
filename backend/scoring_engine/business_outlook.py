"""Business Outlook scoring per docs/SCORING_SYSTEM.md."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_competitive_position,
    score_industry_trends,
    score_management_guidance,
    score_market_opportunities,
    score_structural_risk,
    weighted_module_score,
)
from scoring_engine.weights import BUSINESS_OUTLOOK_WEIGHTS

OUTLOOK_CONFIDENCE_CAP = 0.72


class BusinessOutlookScoreInputs:
    def __init__(
        self,
        *,
        industry_growth_rate: float | None = None,
        industry_growth_trend: float | None = None,
        moat_score: float | None = None,
        market_share_trend: float | None = None,
        advantage_trend: float | None = None,
        pricing_power_score: float | None = None,
        revenue_guidance_trend: float | None = None,
        margin_guidance_trend: float | None = None,
        guidance_accuracy_score: float | None = None,
        product_pipeline_strength: float | None = None,
        geographic_expansion_potential: float | None = None,
        margin_expansion_potential: float | None = None,
        structural_growth_catalyst: float | None = None,
        regulatory_exposure: float | None = None,
        regulatory_trend: float | None = None,
        technological_disruption_risk: float | None = None,
        customer_concentration: float | None = None,
        supplier_concentration: float | None = None,
        cyclicality_exposure: float | None = None,
        structural_decline_risk: float | None = None,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
        confidence_penalty: float = 0.0,
    ) -> None:
        self.industry_growth_rate = industry_growth_rate
        self.industry_growth_trend = industry_growth_trend
        self.moat_score = moat_score
        self.market_share_trend = market_share_trend
        self.advantage_trend = advantage_trend
        self.pricing_power_score = pricing_power_score
        self.revenue_guidance_trend = revenue_guidance_trend
        self.margin_guidance_trend = margin_guidance_trend
        self.guidance_accuracy_score = guidance_accuracy_score
        self.product_pipeline_strength = product_pipeline_strength
        self.geographic_expansion_potential = geographic_expansion_potential
        self.margin_expansion_potential = margin_expansion_potential
        self.structural_growth_catalyst = structural_growth_catalyst
        self.regulatory_exposure = regulatory_exposure
        self.regulatory_trend = regulatory_trend
        self.technological_disruption_risk = technological_disruption_risk
        self.customer_concentration = customer_concentration
        self.supplier_concentration = supplier_concentration
        self.cyclicality_exposure = cyclicality_exposure
        self.structural_decline_risk = structural_decline_risk
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}
        self.confidence_penalty = confidence_penalty


class BusinessOutlookScoreResult:
    def __init__(
        self,
        *,
        score: float | None,
        confidence: float,
        components: list[ComponentScore],
        effective_weights: dict[str, float],
    ) -> None:
        self.score = score
        self.confidence = confidence
        self.components = components
        self.effective_weights = effective_weights


def score_business_outlook(inputs: BusinessOutlookScoreInputs) -> BusinessOutlookScoreResult:
    """
    Calculate the Business Outlook Score (0–100).

    Conservative by design: future prospects carry lower confidence than
    historical statement modules (SCORING_SYSTEM.md).
    """
    component_raw_scores: dict[str, float | None] = {
        "INDUSTRY_TRENDS": score_industry_trends(
            inputs.industry_growth_rate,
            inputs.industry_growth_trend,
        ),
        "COMPETITIVE_POSITION": score_competitive_position(
            moat_score=inputs.moat_score,
            market_share_trend=inputs.market_share_trend,
            advantage_trend=inputs.advantage_trend,
            pricing_power_score=inputs.pricing_power_score,
        ),
        "MANAGEMENT_GUIDANCE": score_management_guidance(
            revenue_guidance_trend=inputs.revenue_guidance_trend,
            margin_guidance_trend=inputs.margin_guidance_trend,
            guidance_accuracy_score=inputs.guidance_accuracy_score,
        ),
        "MARKET_OPPORTUNITIES": score_market_opportunities(
            product_pipeline_strength=inputs.product_pipeline_strength,
            geographic_expansion_potential=inputs.geographic_expansion_potential,
            margin_expansion_potential=inputs.margin_expansion_potential,
            structural_growth_catalyst=inputs.structural_growth_catalyst,
        ),
        "STRUCTURAL_RISK": score_structural_risk(
            regulatory_exposure=inputs.regulatory_exposure,
            technological_disruption_risk=inputs.technological_disruption_risk,
            customer_concentration=inputs.customer_concentration,
            supplier_concentration=inputs.supplier_concentration,
            cyclicality_exposure=inputs.cyclicality_exposure,
            structural_decline_risk=inputs.structural_decline_risk,
            regulatory_trend=inputs.regulatory_trend,
        ),
    }

    names = {
        "INDUSTRY_TRENDS": "Industry Trends",
        "COMPETITIVE_POSITION": "Competitive Position",
        "MANAGEMENT_GUIDANCE": "Management Guidance",
        "MARKET_OPPORTUNITIES": "Market Opportunities",
        "STRUCTURAL_RISK": "Structural Risk",
    }
    raw_values = {
        "INDUSTRY_TRENDS": inputs.industry_growth_rate,
        "COMPETITIVE_POSITION": inputs.moat_score,
        "MANAGEMENT_GUIDANCE": inputs.revenue_guidance_trend,
        "MARKET_OPPORTUNITIES": inputs.product_pipeline_strength,
        "STRUCTURAL_RISK": inputs.regulatory_exposure,
    }

    score, effective = weighted_module_score(component_raw_scores, BUSINESS_OUTLOOK_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in BUSINESS_OUTLOOK_WEIGHTS.items():
        components.append(
            ComponentScore(
                code=code,
                name=names[code],
                weight=effective.get(code, weight),
                raw_value=raw_values[code],
                score=component_raw_scores[code],
                available=component_raw_scores[code] is not None,
                evidence=list(inputs.evidence.get(code, [])),
            )
        )

    confidences = [
        inputs.input_confidence[code]
        for code, value in component_raw_scores.items()
        if value is not None and code in inputs.input_confidence
    ]
    availability = sum(1 for value in component_raw_scores.values() if value is not None) / len(
        component_raw_scores
    )
    base_conf = min(OUTLOOK_CONFIDENCE_CAP, mean(confidences) if confidences else 0.58)
    confidence = clamp_confidence(
        min(
            OUTLOOK_CONFIDENCE_CAP,
            (base_conf or 0.58) * (0.50 + 0.50 * availability) - inputs.confidence_penalty,
        )
    )

    return BusinessOutlookScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
