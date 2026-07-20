"""Structured recommendation module — thin wrapper around RecommendationResult.

Does not re-run aggregators or modules. The AnalysisEngine computes the
recommendation once and this module only packages it for the module list.
"""

from __future__ import annotations

from analysis_engine.base import AnalysisModule
from analysis_engine.schemas import (
    AnalysisModuleResult,
    BusinessQualityResult,
    Finding,
    InvestmentAttractivenessResult,
    RecommendationResult,
)
from canonical_model import CompanyFinancialModel


class RecommendationModule(AnalysisModule):
    """Presentational wrapper only — not a second analytical path."""

    module_id = "recommendation"
    module_version = "1.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        raise RuntimeError(
            "RecommendationModule.analyze() must not run independently. "
            "Use AnalysisEngine.run(), which computes the recommendation once."
        )


def wrap_recommendation(
    recommendation: RecommendationResult,
    business_quality: BusinessQualityResult,
    investment_attractiveness: InvestmentAttractivenessResult,
) -> AnalysisModuleResult:
    """Package an already-computed recommendation as an AnalysisModuleResult."""
    findings = [
        Finding(
            finding_id=reason.reason_id,
            code=reason.code,
            rule_id=None,
            severity="info",
            direction="neutral",
            category="recommendation",
            summary=reason.summary,
            evidence=list(reason.evidence),
            confidence=reason.confidence,
        )
        for reason in recommendation.reasons
    ]

    return AnalysisModuleResult(
        module_name="recommendation",
        module_version="1.0.0",
        status="ok" if recommendation.recommendation != "INSUFFICIENT_DATA" else "skipped",
        score=None,
        confidence=recommendation.confidence,
        findings=findings,
        risks=recommendation.weaknesses,
        opportunities=recommendation.opportunities,
        evidence=[item for reason in recommendation.reasons for item in reason.evidence],
        analyst_adjustments=recommendation.analyst_adjustments,
        coverage={
            "recommendation_code": recommendation.recommendation,
            "recommendation_label": recommendation.recommendation_label,
            "business_quality_classification": business_quality.classification,
            "investment_attractiveness_classification": investment_attractiveness.classification,
        },
        error=(
            "Insufficient data for recommendation."
            if recommendation.recommendation == "INSUFFICIENT_DATA"
            else None
        ),
    )
