"""Investment Attractiveness aggregator — synthesizes valuation + expected return modules.

Consumes only ``AnalysisModuleResult`` objects. Performs no valuation or return math.
"""

from __future__ import annotations

from analysis_engine.business_quality_aggregator import (
    _aggregate_score,
    _collect_opportunities,
    _collect_strengths,
    _collect_weaknesses,
    _merge_adjustments,
)
from analysis_engine.schemas import (
    AnalysisModuleResult,
    InvestmentAttractivenessModuleContribution,
    InvestmentAttractivenessResult,
)
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.weights import INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS

INVESTMENT_ATTRACTIVENESS_MODULE_NAMES: tuple[str, ...] = (
    "valuation",
    "expected_return",
)

_LOW_CONFIDENCE_THRESHOLD = 0.55

_CLASSIFICATION_BANDS: tuple[tuple[float, str, str], ...] = (
    (90.0, "EXCEPTIONAL_OPPORTUNITY", "Exceptional Opportunity"),
    (80.0, "ATTRACTIVE_OPPORTUNITY", "Attractive Opportunity"),
    (60.0, "FAIRLY_VALUED", "Fairly Valued"),
    (50.0, "OVERVALUED", "Overvalued"),
    (0.0, "HIGHLY_OVERVALUED", "Highly Overvalued"),
)


class InvestmentAttractivenessAggregator:
    """Aggregate valuation and expected return module outputs."""

    module_names: tuple[str, ...] = INVESTMENT_ATTRACTIVENESS_MODULE_NAMES
    weights: dict[str, float] = INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS

    def aggregate(self, module_results: list[AnalysisModuleResult]) -> InvestmentAttractivenessResult:
        by_name = {result.module_name: result for result in module_results}
        contributions: list[InvestmentAttractivenessModuleContribution] = []
        skipped_modules: list[str] = []
        low_confidence_modules: list[str] = []

        for module_name in self.module_names:
            result = by_name.get(module_name)
            weight = self.weights[module_name]
            if result is None:
                contributions.append(
                    InvestmentAttractivenessModuleContribution(
                        module_name=module_name,
                        weight=weight,
                        status="skipped",
                    )
                )
                skipped_modules.append(module_name)
                continue

            if result.status == "skipped" or result.score is None:
                contributions.append(
                    InvestmentAttractivenessModuleContribution(
                        module_name=module_name,
                        weight=weight,
                        score=result.score,
                        confidence=result.confidence,
                        status=result.status,
                    )
                )
                if result.status == "skipped":
                    skipped_modules.append(module_name)
                continue

            if result.confidence < _LOW_CONFIDENCE_THRESHOLD:
                low_confidence_modules.append(module_name)

            contributions.append(
                InvestmentAttractivenessModuleContribution(
                    module_name=module_name,
                    weight=weight,
                    score=result.score,
                    confidence=result.confidence,
                    status=result.status,
                )
            )

        score, effective_weights = _aggregate_score(contributions, self.weights)
        confidence = _aggregate_confidence(
            contributions,
            self.weights,
            effective_weights,
            skipped_modules=skipped_modules,
            low_confidence_modules=low_confidence_modules,
        )
        classification, classification_label = _classify(score)

        ia_results = [
            by_name[name]
            for name in self.module_names
            if name in by_name and by_name[name].status == "ok"
        ]

        strengths = _collect_strengths(ia_results)
        weaknesses = _collect_weaknesses(ia_results)
        opportunities = _collect_opportunities(ia_results)
        adjustments = _merge_adjustments(ia_results)

        for contribution in contributions:
            if contribution.module_name in effective_weights:
                contribution.effective_weight = effective_weights[contribution.module_name]

        return InvestmentAttractivenessResult(
            score=score,
            confidence=confidence,
            classification=classification,
            classification_label=classification_label,
            module_contributions=contributions,
            effective_weights=effective_weights,
            strengths=strengths,
            weaknesses=weaknesses,
            opportunities=opportunities,
            analyst_adjustments=adjustments,
            skipped_modules=skipped_modules,
            low_confidence_modules=low_confidence_modules,
            coverage={
                "modules_required": len(self.module_names),
                "modules_scored": sum(
                    1 for item in contributions if item.score is not None and item.status == "ok"
                ),
                "modules_skipped": len(skipped_modules),
                "modules_low_confidence": len(low_confidence_modules),
                "strength_count": len(strengths),
                "weakness_count": len(weaknesses),
                "opportunity_count": len(opportunities),
                "adjustment_count": len(adjustments),
            },
        )


def aggregate_investment_attractiveness(
    module_results: list[AnalysisModuleResult],
) -> InvestmentAttractivenessResult:
    """Convenience wrapper for ``InvestmentAttractivenessAggregator.aggregate``."""
    return InvestmentAttractivenessAggregator().aggregate(module_results)


def _aggregate_confidence(
    contributions: list[InvestmentAttractivenessModuleContribution],
    weights: dict[str, float],
    effective_weights: dict[str, float],
    *,
    skipped_modules: list[str],
    low_confidence_modules: list[str],
) -> float:
    ok_scored = [
        item
        for item in contributions
        if item.module_name in effective_weights and item.status == "ok"
    ]
    if not ok_scored:
        return 0.0

    weighted_conf = sum(
        item.confidence * effective_weights[item.module_name] for item in ok_scored
    )
    availability = len(ok_scored) / len(INVESTMENT_ATTRACTIVENESS_MODULE_NAMES)
    skipped_weight = sum(weights[name] for name in skipped_modules)
    low_conf_penalty = len(low_confidence_modules) * 0.05

    adjusted = weighted_conf * (0.55 + 0.45 * availability)
    adjusted -= skipped_weight * 0.20
    adjusted -= low_conf_penalty
    return clamp_confidence(adjusted)


def _classify(score: float | None) -> tuple[str, str]:
    if score is None:
        return "INSUFFICIENT_DATA", "Insufficient Data"
    for threshold, code, label in _CLASSIFICATION_BANDS:
        if score >= threshold:
            return code, label
    return "HIGHLY_OVERVALUED", "Highly Overvalued"
