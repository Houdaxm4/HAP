"""Recommendation engine — combines Business Quality and Investment Attractiveness.

Deterministic synthesis only. No narrative generation or AI reasoning.
"""

from __future__ import annotations

from analysis_engine.business_quality_aggregator import (
    _dedupe_findings,
    _dedupe_opportunities,
    _dedupe_risks,
    _strength_sort_key,
    _weakness_sort_key,
)
from analysis_engine.schemas import (
    AnalysisModuleResult,
    BusinessQualityResult,
    Evidence,
    Finding,
    InvestmentAttractivenessResult,
    OpportunityItem,
    RecommendationReason,
    RecommendationResult,
    RiskItem,
)
from analysis_engine.utils import clamp_confidence, mean

_BQ_AVOID_THRESHOLD = 60.0
_IA_AVOID_THRESHOLD = 50.0

_RECOMMENDATION_LABELS: dict[str, str] = {
    "STRONG_BUY": "Strong Buy",
    "BUY": "Buy",
    "HOLD": "Hold",
    "WATCH": "Watch",
    "WAIT_FOR_BETTER_PRICE": "Wait For Better Price",
    "AVOID": "Avoid",
    "INSUFFICIENT_DATA": "Insufficient Data",
}


class RecommendationEngine:
    """Produce final HAP recommendation from completed synthesis results."""

    def recommend(
        self,
        business_quality: BusinessQualityResult,
        investment_attractiveness: InvestmentAttractivenessResult,
        module_results: list[AnalysisModuleResult] | None = None,
    ) -> RecommendationResult:
        bq_score = business_quality.score
        ia_score = investment_attractiveness.score

        reasons = _build_reasons(business_quality, investment_attractiveness, module_results or [])
        code, label = _determine_recommendation(bq_score, ia_score, reasons)

        strengths = _dedupe_findings(
            sorted(
                business_quality.strengths + investment_attractiveness.strengths,
                key=_strength_sort_key,
                reverse=True,
            )
        )
        weaknesses = _dedupe_risks(
            sorted(
                business_quality.weaknesses + investment_attractiveness.weaknesses,
                key=_weakness_sort_key,
            )
        )
        opportunities = _dedupe_opportunities(
            business_quality.opportunities + investment_attractiveness.opportunities
        )
        adjustments = _merge_all_adjustments(business_quality, investment_attractiveness)

        confidence = _recommendation_confidence(business_quality, investment_attractiveness, code)

        return RecommendationResult(
            recommendation=code,  # type: ignore[arg-type]
            recommendation_label=label,
            confidence=confidence,
            business_quality_score=bq_score,
            investment_attractiveness_score=ia_score,
            business_quality_classification=business_quality.classification,
            investment_attractiveness_classification=investment_attractiveness.classification,
            reasons=reasons,
            strengths=strengths,
            weaknesses=weaknesses,
            opportunities=opportunities,
            analyst_adjustments=adjustments,
            coverage={
                "business_quality_confidence": business_quality.confidence,
                "investment_attractiveness_confidence": investment_attractiveness.confidence,
                "reason_count": len(reasons),
                "strength_count": len(strengths),
                "weakness_count": len(weaknesses),
                "opportunity_count": len(opportunities),
                "adjustment_count": len(adjustments),
                "bq_skipped_modules": list(business_quality.skipped_modules),
                "ia_skipped_modules": list(investment_attractiveness.skipped_modules),
            },
        )


def generate_recommendation(
    business_quality: BusinessQualityResult,
    investment_attractiveness: InvestmentAttractivenessResult,
    module_results: list[AnalysisModuleResult] | None = None,
) -> RecommendationResult:
    """Convenience wrapper for ``RecommendationEngine.recommend``."""
    return RecommendationEngine().recommend(
        business_quality,
        investment_attractiveness,
        module_results,
    )


def _determine_recommendation(
    bq_score: float | None,
    ia_score: float | None,
    reasons: list[RecommendationReason],
) -> tuple[str, str]:
    if bq_score is None or ia_score is None:
        return "INSUFFICIENT_DATA", _RECOMMENDATION_LABELS["INSUFFICIENT_DATA"]

    if bq_score < _BQ_AVOID_THRESHOLD:
        return "AVOID", _RECOMMENDATION_LABELS["AVOID"]

    if ia_score < _IA_AVOID_THRESHOLD:
        return "AVOID", _RECOMMENDATION_LABELS["AVOID"]

    if bq_score >= 90 and ia_score >= 90:
        return "STRONG_BUY", _RECOMMENDATION_LABELS["STRONG_BUY"]
    if bq_score >= 90 and ia_score >= 70:
        return "BUY", _RECOMMENDATION_LABELS["BUY"]
    if bq_score >= 90 and ia_score >= 60:
        return "WATCH", _RECOMMENDATION_LABELS["WATCH"]
    if bq_score >= 90:
        return "WAIT_FOR_BETTER_PRICE", _RECOMMENDATION_LABELS["WAIT_FOR_BETTER_PRICE"]

    if bq_score >= 70 and ia_score >= 80:
        return "BUY", _RECOMMENDATION_LABELS["BUY"]
    if bq_score >= 70 and ia_score >= 60:
        return "HOLD", _RECOMMENDATION_LABELS["HOLD"]
    if bq_score >= 70:
        return "WATCH", _RECOMMENDATION_LABELS["WATCH"]

    if bq_score >= 60 and ia_score >= 80:
        return "HOLD", _RECOMMENDATION_LABELS["HOLD"]
    if bq_score >= 60 and ia_score >= 50:
        return "WATCH", _RECOMMENDATION_LABELS["WATCH"]

    if any(reason.code == "SPECULATIVE_VALUE_TRAP" for reason in reasons):
        return "WATCH", _RECOMMENDATION_LABELS["WATCH"]

    return "AVOID", _RECOMMENDATION_LABELS["AVOID"]


def _build_reasons(
    business_quality: BusinessQualityResult,
    investment_attractiveness: InvestmentAttractivenessResult,
    module_results: list[AnalysisModuleResult],
) -> list[RecommendationReason]:
    reasons: list[RecommendationReason] = []
    bq = business_quality.score
    ia = investment_attractiveness.score

    if bq is not None:
        reasons.append(
            RecommendationReason(
                reason_id="rec:bq:score",
                code="BUSINESS_QUALITY_SCORE",
                category="business_quality",
                summary=f"Business Quality score is {bq:.1f} ({business_quality.classification_label}).",
                business_quality_score=bq,
                investment_attractiveness_score=ia,
                evidence=_score_evidence("BUSINESS_QUALITY_SCORE", bq, business_quality.confidence),
                confidence=business_quality.confidence,
            )
        )
    if ia is not None:
        reasons.append(
            RecommendationReason(
                reason_id="rec:ia:score",
                code="INVESTMENT_ATTRACTIVENESS_SCORE",
                category="investment_attractiveness",
                summary=(
                    f"Investment Attractiveness score is {ia:.1f} "
                    f"({investment_attractiveness.classification_label})."
                ),
                business_quality_score=bq,
                investment_attractiveness_score=ia,
                evidence=_score_evidence(
                    "INVESTMENT_ATTRACTIVENESS_SCORE",
                    ia,
                    investment_attractiveness.confidence,
                ),
                confidence=investment_attractiveness.confidence,
            )
        )

    if bq is not None and bq < _BQ_AVOID_THRESHOLD:
        reasons.append(
            RecommendationReason(
                reason_id="rec:bq:weak",
                code="WEAK_BUSINESS_QUALITY",
                category="business_quality",
                summary="Business Quality is below the minimum threshold for a positive recommendation.",
                business_quality_score=bq,
                investment_attractiveness_score=ia,
                evidence=_score_evidence("BUSINESS_QUALITY_SCORE", bq, business_quality.confidence),
                confidence=business_quality.confidence,
            )
        )

    if ia is not None and ia < _IA_AVOID_THRESHOLD:
        reasons.append(
            RecommendationReason(
                reason_id="rec:ia:poor",
                code="POOR_INVESTMENT_ATTRACTIVENESS",
                category="investment_attractiveness",
                summary="Investment Attractiveness is below the avoid threshold at the current price.",
                business_quality_score=bq,
                investment_attractiveness_score=ia,
                evidence=_score_evidence(
                    "INVESTMENT_ATTRACTIVENESS_SCORE",
                    ia,
                    investment_attractiveness.confidence,
                ),
                confidence=investment_attractiveness.confidence,
            )
        )

    if bq is not None and ia is not None and bq >= 90 and ia < 70:
        reasons.append(
            RecommendationReason(
                reason_id="rec:syn:quality_without_value",
                code="QUALITY_WITHOUT_ATTRACTIVE_PRICE",
                category="synthesis",
                summary="Excellent business quality but insufficient margin of safety at today's price.",
                business_quality_score=bq,
                investment_attractiveness_score=ia,
                evidence=_synthesis_evidence(bq, ia),
                confidence=min(business_quality.confidence, investment_attractiveness.confidence),
            )
        )

    if bq is not None and ia is not None and bq < 70 and ia >= 80:
        reasons.append(
            RecommendationReason(
                reason_id="rec:syn:speculative",
                code="SPECULATIVE_VALUE_TRAP",
                category="synthesis",
                summary="Attractive price but business quality is below threshold; requires analyst review.",
                business_quality_score=bq,
                investment_attractiveness_score=ia,
                evidence=_synthesis_evidence(bq, ia),
                confidence=min(business_quality.confidence, investment_attractiveness.confidence),
            )
        )

    if bq is not None and ia is not None and bq >= 90 and ia >= 90:
        reasons.append(
            RecommendationReason(
                reason_id="rec:syn:strong_buy",
                code="HIGH_QUALITY_ATTRACTIVE_PRICE",
                category="synthesis",
                summary="High business quality and highly attractive valuation support a strong buy case.",
                business_quality_score=bq,
                investment_attractiveness_score=ia,
                evidence=_synthesis_evidence(bq, ia),
                confidence=min(business_quality.confidence, investment_attractiveness.confidence),
            )
        )

    for finding in business_quality.strengths[:3]:
        reasons.append(_reason_from_finding(finding, bq, ia, category="business_quality"))
    for finding in investment_attractiveness.strengths[:3]:
        reasons.append(_reason_from_finding(finding, bq, ia, category="investment_attractiveness"))

    for risk in (business_quality.weaknesses + investment_attractiveness.weaknesses)[:5]:
        reasons.append(_reason_from_risk(risk, bq, ia))

    return _dedupe_reasons(reasons)


def _reason_from_finding(
    finding: Finding,
    bq: float | None,
    ia: float | None,
    *,
    category: str,
) -> RecommendationReason:
    return RecommendationReason(
        reason_id=f"rec:finding:{finding.finding_id}",
        code=finding.code,
        category=category,  # type: ignore[arg-type]
        summary=finding.summary,
        business_quality_score=bq,
        investment_attractiveness_score=ia,
        supporting_module=finding.category,
        supporting_rule_id=finding.rule_id,
        evidence=list(finding.evidence),
        confidence=finding.confidence,
    )


def _reason_from_risk(risk: RiskItem, bq: float | None, ia: float | None) -> RecommendationReason:
    category: str = "business_quality"
    if risk.code in {
        "POTENTIAL_OVERVALUATION",
        "NEGATIVE_EXPECTED_RETURN",
        "VALUATION_HEADWIND",
        "INDEX_SUPERIOR",
    }:
        category = "investment_attractiveness"
    return RecommendationReason(
        reason_id=f"rec:risk:{risk.risk_id}",
        code=risk.code,
        category=category,  # type: ignore[arg-type]
        summary=risk.summary,
        business_quality_score=bq,
        investment_attractiveness_score=ia,
        evidence=list(risk.evidence),
        confidence=risk.confidence,
    )


def _recommendation_confidence(
    business_quality: BusinessQualityResult,
    investment_attractiveness: InvestmentAttractivenessResult,
    recommendation_code: str,
) -> float:
    if recommendation_code == "INSUFFICIENT_DATA":
        return 0.0
    base = mean([business_quality.confidence, investment_attractiveness.confidence]) or 0.0
    penalty = 0.0
    if business_quality.skipped_modules:
        penalty += 0.08 * len(business_quality.skipped_modules)
    if investment_attractiveness.skipped_modules:
        penalty += 0.10 * len(investment_attractiveness.skipped_modules)
    if recommendation_code in {"WATCH", "WAIT_FOR_BETTER_PRICE"}:
        penalty += 0.03
    if recommendation_code == "AVOID" and (
        business_quality.score is None or investment_attractiveness.score is None
    ):
        penalty += 0.05
    return clamp_confidence(base - penalty)


def _merge_all_adjustments(
    business_quality: BusinessQualityResult,
    investment_attractiveness: InvestmentAttractivenessResult,
) -> list:
    from analysis_engine.business_quality_aggregator import _merge_adjustments

    combined_results = []
    seen: set[str] = set()
    for proposal in business_quality.analyst_adjustments + investment_attractiveness.analyst_adjustments:
        key = (proposal.action, proposal.target or "", proposal.rationale_code)
        if key in seen:
            continue
        seen.add(key)
        combined_results.append(proposal)
    return sorted(combined_results, key=lambda item: (-item.confidence, item.adjustment_id))


def _dedupe_reasons(reasons: list[RecommendationReason]) -> list[RecommendationReason]:
    seen: set[str] = set()
    unique: list[RecommendationReason] = []
    for reason in reasons:
        if reason.reason_id in seen:
            continue
        seen.add(reason.reason_id)
        unique.append(reason)
    return unique


def _score_evidence(metric: str, value: float, confidence: float) -> list[Evidence]:
    return [
        Evidence(
            kind="derived_metric",
            label=metric,
            metric=metric,
            value=value,
            confidence=confidence,
            source="recommendation_engine",
        )
    ]


def _synthesis_evidence(bq: float, ia: float) -> list[Evidence]:
    return [
        Evidence(
            kind="derived_metric",
            label="BUSINESS_QUALITY_SCORE",
            metric="BUSINESS_QUALITY_SCORE",
            value=bq,
            confidence=0.85,
            source="recommendation_engine",
        ),
        Evidence(
            kind="derived_metric",
            label="INVESTMENT_ATTRACTIVENESS_SCORE",
            metric="INVESTMENT_ATTRACTIVENESS_SCORE",
            value=ia,
            confidence=0.85,
            source="recommendation_engine",
        ),
    ]
