"""Business Quality aggregator — synthesizes completed BQ module results.

Consumes only ``AnalysisModuleResult`` objects. Performs no financial
calculations, metric recomputation, or rule evaluation.
"""

from __future__ import annotations

from analysis_engine.schemas import (
    AnalystAdjustmentProposal,
    AnalysisModuleResult,
    BusinessQualityModuleContribution,
    BusinessQualityResult,
    Evidence,
    Finding,
    OpportunityItem,
    RiskItem,
)
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.weights import BUSINESS_QUALITY_WEIGHTS

BUSINESS_QUALITY_MODULE_NAMES: tuple[str, ...] = (
    "profitability",
    "growth",
    "cash_flow",
    "balance_sheet",
    "capital_allocation",
    "business_outlook",
)

_LOW_CONFIDENCE_THRESHOLD = 0.55

_SEVERITY_RANK: dict[str, int] = {
    "critical": 5,
    "warning": 4,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
    "positive": 6,
}

_PRIORITY_RANK: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
}

_CLASSIFICATION_BANDS: tuple[tuple[float, str, str], ...] = (
    (90.0, "EXCEPTIONAL_BUSINESS", "Exceptional Business"),
    (80.0, "EXCELLENT_BUSINESS", "Excellent Business"),
    (70.0, "HIGH_QUALITY_BUSINESS", "High Quality Business"),
    (60.0, "AVERAGE_BUSINESS", "Average Business"),
    (0.0, "WEAK_BUSINESS", "Weak Business"),
)


class BusinessQualityAggregator:
    """Aggregate Business Quality module outputs into a single synthesis result."""

    module_names: tuple[str, ...] = BUSINESS_QUALITY_MODULE_NAMES
    weights: dict[str, float] = BUSINESS_QUALITY_WEIGHTS

    def aggregate(self, module_results: list[AnalysisModuleResult]) -> BusinessQualityResult:
        by_name = {result.module_name: result for result in module_results}
        contributions: list[BusinessQualityModuleContribution] = []
        skipped_modules: list[str] = []
        low_confidence_modules: list[str] = []

        for module_name in self.module_names:
            result = by_name.get(module_name)
            weight = self.weights[module_name]
            if result is None:
                contributions.append(
                    BusinessQualityModuleContribution(
                        module_name=module_name,
                        weight=weight,
                        status="skipped",
                    )
                )
                skipped_modules.append(module_name)
                continue

            if result.status == "skipped" or result.score is None:
                contributions.append(
                    BusinessQualityModuleContribution(
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
                BusinessQualityModuleContribution(
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

        bq_results = [
            by_name[name]
            for name in self.module_names
            if name in by_name and by_name[name].status == "ok"
        ]

        strengths = _collect_strengths(bq_results)
        weaknesses = _collect_weaknesses(bq_results)
        opportunities = _collect_opportunities(bq_results)
        adjustments = _merge_adjustments(bq_results)

        for contribution in contributions:
            if contribution.module_name in effective_weights:
                contribution.effective_weight = effective_weights[contribution.module_name]

        return BusinessQualityResult(
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


def aggregate_business_quality(
    module_results: list[AnalysisModuleResult],
) -> BusinessQualityResult:
    """Convenience wrapper for ``BusinessQualityAggregator.aggregate``."""
    return BusinessQualityAggregator().aggregate(module_results)


def _aggregate_score(
    contributions: list[BusinessQualityModuleContribution],
    weights: dict[str, float],
) -> tuple[float | None, dict[str, float]]:
    scored = {
        item.module_name: item.score
        for item in contributions
        if item.score is not None and item.status == "ok"
    }
    if not scored:
        return None, {}
    weight_sum = sum(weights[name] for name in scored)
    if weight_sum <= 0:
        return None, {}
    effective = {name: weights[name] / weight_sum for name in scored}
    score = sum(scored[name] * effective[name] for name in scored)
    return round(max(0.0, min(100.0, score)), 2), effective


def _aggregate_confidence(
    contributions: list[BusinessQualityModuleContribution],
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
    availability = len(ok_scored) / len(BUSINESS_QUALITY_MODULE_NAMES)
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
    return "WEAK_BUSINESS", "Weak Business"


def _collect_strengths(module_results: list[AnalysisModuleResult]) -> list[Finding]:
    findings: list[Finding] = []
    for result in module_results:
        for finding in result.findings:
            if finding.severity == "positive" or finding.direction == "positive":
                findings.append(finding)
    findings.sort(key=_strength_sort_key, reverse=True)
    return _dedupe_findings(findings)


def _collect_weaknesses(module_results: list[AnalysisModuleResult]) -> list[RiskItem]:
    risks: list[RiskItem] = []
    for result in module_results:
        risks.extend(result.risks)
    risks.sort(key=_weakness_sort_key)
    return _dedupe_risks(risks)


def _collect_opportunities(module_results: list[AnalysisModuleResult]) -> list[OpportunityItem]:
    items: list[OpportunityItem] = []
    for result in module_results:
        items.extend(result.opportunities)
    items.sort(key=_opportunity_sort_key, reverse=True)
    return _dedupe_opportunities(items)


def _merge_adjustments(
    module_results: list[AnalysisModuleResult],
) -> list[AnalystAdjustmentProposal]:
    merged: dict[tuple[str, str, str], AnalystAdjustmentProposal] = {}
    for result in module_results:
        for proposal in result.analyst_adjustments:
            key = (
                proposal.action,
                proposal.target or "",
                proposal.rationale_code,
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = proposal.model_copy(deep=True)
                continue
            merged[key] = _merge_adjustment_pair(existing, proposal)
    ordered = sorted(merged.values(), key=_adjustment_sort_key, reverse=True)
    return ordered


def _merge_adjustment_pair(
    left: AnalystAdjustmentProposal,
    right: AnalystAdjustmentProposal,
) -> AnalystAdjustmentProposal:
    finding_ids = list(dict.fromkeys(left.related_finding_ids + right.related_finding_ids))
    priority = left.priority
    if _PRIORITY_RANK.get(right.priority, 0) > _PRIORITY_RANK.get(left.priority, 0):
        priority = right.priority
    confidence = max(left.confidence, right.confidence)
    return left.model_copy(
        update={
            "related_finding_ids": finding_ids,
            "priority": priority,
            "confidence": confidence,
        }
    )


def _strength_sort_key(finding: Finding) -> tuple[float, float, float, str]:
    evidence_conf = _mean_evidence_confidence(finding.evidence) or finding.confidence
    return (
        float(_SEVERITY_RANK.get(finding.severity, 0)),
        finding.confidence,
        evidence_conf,
        finding.finding_id,
    )


def _weakness_sort_key(risk: RiskItem) -> tuple[float, float, float, str]:
    evidence_conf = _mean_evidence_confidence(risk.evidence) or risk.confidence
    return (
        -float(_SEVERITY_RANK.get(risk.severity, 0)),
        -risk.confidence,
        -evidence_conf,
        risk.risk_id,
    )


def _opportunity_sort_key(item: OpportunityItem) -> tuple[float, float, str]:
    evidence_conf = _mean_evidence_confidence(item.evidence) or item.confidence
    return (item.confidence, evidence_conf, item.opportunity_id)


def _adjustment_sort_key(proposal: AnalystAdjustmentProposal) -> tuple[int, float, str]:
    return (
        _PRIORITY_RANK.get(proposal.priority, 0),
        proposal.confidence,
        proposal.adjustment_id,
    )


def _mean_evidence_confidence(evidence: list[Evidence]) -> float | None:
    values = [item.confidence for item in evidence if item.confidence is not None]
    return mean(values) if values else None


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    unique: list[Finding] = []
    for finding in findings:
        if finding.finding_id in seen:
            continue
        seen.add(finding.finding_id)
        unique.append(finding)
    return unique


def _dedupe_risks(risks: list[RiskItem]) -> list[RiskItem]:
    seen: set[str] = set()
    unique: list[RiskItem] = []
    for risk in risks:
        if risk.risk_id in seen:
            continue
        seen.add(risk.risk_id)
        unique.append(risk)
    return unique


def _dedupe_opportunities(items: list[OpportunityItem]) -> list[OpportunityItem]:
    seen: set[str] = set()
    unique: list[OpportunityItem] = []
    for item in items:
        if item.opportunity_id in seen:
            continue
        seen.add(item.opportunity_id)
        unique.append(item)
    return unique
